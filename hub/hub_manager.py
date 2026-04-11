import paho.mqtt.client as mqtt
import json
import os
import sys
import subprocess
import time
import threading
from datetime import datetime

# --- パス解決 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
wildlink_root = os.path.dirname(current_dir) # プロジェクトのルート (wildlink/)

# ルートディレクトリをパスに追加（既にメインマネージャー等で採用している方式）
if wildlink_root not in sys.path:
    sys.path.insert(0, wildlink_root)
common_path = os.path.join(wildlink_root, "common")
sys.path.append(common_path)

# --- WildLink 共通モジュールのインポート ---
from common import config_loader  # 🌟 これを追加！
from db_bridge import DBBridge
from logger_config import get_logger

logger = get_logger("hub_manager")
MQTT_PREFIX = getattr(config_loader, 'MQTT_PREFIX', 'wildlink')
GROUP_ID    = getattr(config_loader, 'GROUP_ID', 'home_internal')

class WildLinkHubManager:
    """
    WildLink Event Standard (WES) 2026 準拠
    役割: 全ノードのコマンド一元配送、ステータス同期、およびイベント中継（UI連携）。
    
    【WES 2026: 履歴重視・信頼性設計】
    - コマンド配送(sent) -> 受領確認(acknowledged) -> 最終決着(completed/error) の遷移を管理。
    - 正常終了だけでなく、エラーやタイムアウト時も 'completed_at' に時刻を刻み、
      「いつ処理が打ち切られたか」を明確にします。
    """
    def __init__(self):
        self.db = DBBridge()
        # MQTTクライアント初期化 (Callback API V1)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="wildlink_hub")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # サブプロセスの管理
        self.processes = {
            "stream_rx": {"path": os.path.join(current_dir, "wmp_stream_rx.py"), "proc": None, "id": "hub_001"},
            "status_eng": {"path": os.path.join(current_dir, "status_engine.py"), "proc": None, "id": "hub_001"}
        }
        self.running = True

    # ---------------------------------------------------------
    # メッセージ受信ハンドラ (Hubの耳)
    # ---------------------------------------------------------

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("🌐 Hub Manager Connected Successfully.")
            
            # UIからのキック（目覚まし）通知を購読
            client.subscribe("system/hub/kick")
            
            # 全ノードのレスポンス(res)とイベント(event)を購読
            client.subscribe(f"{MQTT_PREFIX}/{GROUP_ID}/+/+/res")
            client.subscribe(f"{MQTT_PREFIX}/{GROUP_ID}/+/+/event")
        else:
            logger.error(f"❌ Connection failed with code {rc}")

    def on_message(self, client, userdata, msg):
        """
        受信メッセージの解析とDB・UI・Nodeへの振り分け
        """
        try:
            # 1. UIからのキック通知
            if msg.topic == "system/hub/kick":
                logger.info("⚡ [HUB] Received kick from UI. Checking pending commands...")
                self._dispatch_pending_commands()
                return

            # 2. Nodeからのメッセージ (res / event)
            parts = msg.topic.split('/')
            if len(parts) < 5 or parts[0] != MQTT_PREFIX: 
                return
            
            sys_id   = parts[2]
            vst_role = parts[3]
            msg_type = parts[4] # res, event

            payload = json.loads(msg.payload.decode())
            if not isinstance(payload, dict): return

            # [res] トピック: コマンド進捗と物理状態の同期
            if msg_type == 'res':
                cmd_status = payload.get('cmd_status') # acknowledged / completed / failed / error
                val_status = payload.get('val_status') # idle / streaming / error
                # Node側からは ref_cmd_id または cmd_id として返ってくることを想定
                ref_id = payload.get('ref_cmd_id') or payload.get('cmd_id')

                # A. 物理状態の同期 (node_status_currentテーブル)
                if val_status:
                    self.db.update_node_status(sys_id, vst_role, payload)

                # B. コマンド進捗報告の記録 (node_commandsテーブル)
                if ref_id and cmd_status:
                    self._handle_command_lifecycle(ref_id, cmd_status, payload)

            # [event] トピック: ログ記録
            elif msg_type == 'event':
                event_name = payload.get('event')
                logger.info(f"📥 [event] {sys_id}:{vst_role} -> {event_name}")

                # イベントログをDBに保存
                self.db.insert_event_log(sys_id, vst_role, payload)

                # UI連携: 特定のイベントをUIに中継
                if event_name in ["streaming_started", "stream_ready"]:
                    self._kick_ui_panel(sys_id, vst_role, payload)

        except Exception as e:
            logger.error(f"❌ Message Handler Error: {e}")

    # ---------------------------------------------------------
    # コマンド配送ロジック (Hub -> Node)
    # ---------------------------------------------------------

    def _dispatch_pending_commands(self):
        """
        DBから未送信(pending)のコマンドを拾い、対象Nodeへ配送。
        """
        try:
            commands = self.db.fetch_pending_commands() 
            if not commands:
                logger.info("ℹ️ No pending commands found in DB.")
                return

            for cmd in commands:
                cmd_id = cmd['id']
                target_sys = cmd['sys_id'] 
                vst_role = cmd.get('vst_role_name') or 'system' 
                
                topic = f"{MQTT_PREFIX}/{GROUP_ID}/{target_sys}/{vst_role}/cmd"
                
                try:
                    payload = json.loads(cmd['cmd_json']) if cmd['cmd_json'] else {}
                except:
                    payload = {"raw_payload": cmd['cmd_json']}
                
                # 応答紐付け用の ID 注入
                payload['cmd_id'] = cmd_id
                json_payload = json.dumps(payload, ensure_ascii=False)
                
                logger.info(f"📤 Dispatching [ID:{cmd_id}] to {topic}")
                
                # 送信し、即座に DBを 'sent' (sent_at記録) に更新
                self.client.publish(topic, json_payload, qos=1)
                self.db.update_command_status(cmd_id, "sent")
                
        except Exception as e:
            logger.error(f"❌ Dispatcher Error: {e}")

    # ---------------------------------------------------------
    # 内部ロジック (DB更新・UI連携)
    # ---------------------------------------------------------

    def _handle_command_lifecycle(self, cmd_id, status, payload):
        """
        WES 2026 厳密ステータス管理
        """
        # 1. Acknowledged (受領確認)
        if status == "acknowledged":
            logger.info(f"✅ [ACK] Command {cmd_id} acknowledged by node.")
            self.db.mark_command_acknowledged(cmd_id)
        
        # 2. Completed (正常終了)
        elif status == "completed" or status == "success":
            logger.info(f"🏁 [FIN] Command {cmd_id} completed successfully.")
            
            # 🌟 修正：設定値を「payload直下」または「log_extの中」から探す
            log_ext = payload.get('log_ext') or {}
            res_val = payload.get('val_res_payload') or log_ext.get('val_res_payload')

            if res_val:
                logger.info(f"💾 Updating node_configs with: {res_val}")
                self.db.sync_node_config_from_payload(cmd_id, res_val)

            self.db.finalize_command(
                cmd_id=cmd_id,
                status="completed",
                log_msg=payload.get('log_msg', 'Completed'),
                log_code=payload.get('log_code', 200),
                res_payload=payload
            )
        
        # 3. Failed / Error (異常終了)
        elif status in ["failed", "error"]:
            logger.error(f"⚠️ [ERR] Command {cmd_id} failed reported by node.")
            # WES 2026 では、エラー時も finalized として時刻(completed_at)を刻む
            self.db.finalize_command(
                cmd_id=cmd_id,
                status="error",
                log_msg=payload.get('log_msg', 'Failed/Error reported'),
                log_code=payload.get('log_code', 500),
                res_payload=payload
            )

    def _kick_ui_panel(self, sys_id, vst_role, payload):
        """[UI連携] パネル表示指示"""
        ui_cmd = {
            "action": "open_panel",
            "target_role": vst_role,
            "net_port": payload.get("net_port"),
            "timestamp": time.time()
        }
        self.client.publish("gui/control", json.dumps(ui_cmd))
        logger.info(f"🚀 UI Kick sent: Open panel for {vst_role}")

    # ---------------------------------------------------------
    # サブプロセス管理
    # ---------------------------------------------------------

    def _spawn_process(self, name):
        conf = self.processes[name]
        env = os.environ.copy()
        env["SYS_ID"] = conf["id"]
        
        logger.info(f"🎬 Starting {name}: {conf['path']}")
        return subprocess.Popen(
            ["python3", conf["path"]],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            cwd=wildlink_root 
        )

    def manage_sub_processes(self, should_run):
        for name, info in self.processes.items():
            if should_run:
                if info["proc"] is None or info["proc"].poll() is not None:
                    info["proc"] = self._spawn_process(name)
            else:
                if info["proc"] and info["proc"].poll() is None:
                    info["proc"].terminate()
                    info["proc"] = None

    def run(self):
        self.manage_sub_processes(True)
        broker = os.getenv("MQTT_BROKER", "localhost")
        try:
            self.client.connect(broker, 1883, 60)
        except Exception as e:
            logger.error(f"❌ MQTT Connection Error: {e}")
            return

        self.client.loop_start()
        
        logger.info(f"📡 Hub Manager Running. System ID: {os.getenv('SYS_ID', 'hub_001')}")
        
        try:
            while self.running:
                self.manage_sub_processes(True)
                time.sleep(5)
        except KeyboardInterrupt:
            self.running = False
            self.manage_sub_processes(False)
            self.client.loop_stop()

if __name__ == "__main__":
    if not os.getenv("SYS_ID"):
        os.environ["SYS_ID"] = "hub_001"
    WildLinkHubManager().run()