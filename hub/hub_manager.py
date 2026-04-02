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
wildlink_root = os.path.dirname(current_dir)
common_path = os.path.join(wildlink_root, "common")
sys.path.append(common_path)

from db_bridge import DBBridge
from logger_config import get_logger

logger = get_logger("hub_manager")

class WildLinkHubManager:
    """
    WildLink Event Standard (WES) 2026 準拠
    役割: 全ノードのコマンド配送、ステータス同期、およびイベント中継（UI連携）。
    """
    def __init__(self):
        self.db = DBBridge()
        # MQTTクライアント初期化
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
    # コマンド配送 (Hub -> Node)
    # ---------------------------------------------------------

    def command_dispatcher_loop(self):
        """DBから未送信のコマンドを拾い、各Nodeの /cmd トピックへ配送する"""
        logger.info("📨 Command Dispatcher Loop active.")
        while self.running:
            try:
                commands = self.db.fetch_pending_commands() 
                for cmd in commands:
                    cmd_id = cmd['id']
                    target_sys = cmd['sys_id'] 
                    # WES 2026: vst_role_name をトピックに使用
                    vst_role = cmd.get('vst_role_name') or 'system' 
                    
                    topic = f"nodes/{target_sys}/{vst_role}/cmd"
                    
                    try:
                        payload = json.loads(cmd['cmd_json']) if cmd['cmd_json'] else {}
                    except:
                        payload = {"raw_payload": cmd['cmd_json']}
                    
                    # 応答紐付け用の ID 注入
                    payload['cmd_id'] = cmd_id
                    
                    json_payload = json.dumps(payload, ensure_ascii=False)
                    logger.info(f"📤 Dispatching [ID:{cmd_id}] to {topic}")
                    
                    self.client.publish(topic, json_payload, qos=1)
                    self.db.update_command_status(cmd_id, "sent")
                    
            except Exception as e:
                logger.error(f"❌ Dispatcher Error: {e}")
            time.sleep(1)

    # ---------------------------------------------------------
    # メッセージ受信ハンドラ (Node -> Hub)
    # ---------------------------------------------------------

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("🌐 Hub Manager Connected Successfully.")
            # 全ノードのレスポンスとイベントを購読
            client.subscribe("nodes/+/+/res")
            client.subscribe("nodes/+/+/event")
        else:
            logger.error(f"❌ Connection failed with code {rc}")

    def on_message(self, client, userdata, msg):
        """
        受信メッセージの解析とDB・UIへの振り分け
        """
        try:
            parts = msg.topic.split('/')
            if len(parts) < 4: return
            
            sys_id   = parts[1]
            vst_role = parts[2]
            msg_type = parts[3] # res, event

            payload = json.loads(msg.payload.decode())
            if not isinstance(payload, dict): return

            # -------------------------------------------------------------
            # 1. /res トピック: コマンド結果と物理状態の同期
            # -------------------------------------------------------------
            if msg_type == 'res':
                cmd_status = payload.get('cmd_status') # acknowledged / completed / failed
                val_status = payload.get('val_status') # idle / streaming / error
                ref_id = payload.get('ref_cmd_id')

                # A. 物理状態の同期 (node_status_currentテーブル)
                if val_status:
                    self.db.update_node_status(sys_id, vst_role, payload)

                # B. コマンド完了報告の記録 (node_commandsテーブル)
                if ref_id and cmd_status:
                    self._handle_command_lifecycle(ref_id, cmd_status, payload)

            # -------------------------------------------------------------
            # 2. /event トピック: ログ記録とUIアクションのトリガー
            # -------------------------------------------------------------
            elif msg_type == 'event':
                event_name = payload.get('event')
                logger.info(f"📥 [event] {sys_id}:{vst_role} -> {event_name}")

                # イベントログをDBに保存
                self.db.insert_event_log(sys_id, vst_role, payload)

                # 【新規】UI連携: 配信開始イベントをUI制御トピックに中継
                if event_name == "streaming_started":
                    self._kick_ui_panel(sys_id, vst_role, payload)

        except Exception as e:
            logger.error(f"❌ Message Handler Error: {e}")

    # ---------------------------------------------------------
    # 内部ロジック
    # ---------------------------------------------------------

    def _handle_command_lifecycle(self, cmd_id, status, payload):
        """コマンドの進捗(node_commands)をDBに反映する"""
        if status == "acknowledged":
            self.db.mark_command_acknowledged(cmd_id)
        elif status == "completed":
            self.db.finalize_command(
                cmd_id=cmd_id,
                status="success",
                log_msg=payload.get('log_msg', 'Completed'),
                log_code=payload.get('log_code', 200),
                res_payload=payload
            )
        elif status == "failed":
            self.db.finalize_command(
                cmd_id=cmd_id,
                status="error",
                log_msg=payload.get('log_msg', 'Failed'),
                log_code=payload.get('log_code', 500),
                res_payload=payload
            )

    def _kick_ui_panel(self, sys_id, vst_role, payload):
        """
        [UI連携] 配信開始を検知した際、ブラウザUIに対してパネルを開くようMQTTで指示。
        """
        ui_cmd = {
            "action": "open_panel",
            "target_role": vst_role,
            "net_port": payload.get("net_port"),
            "timestamp": time.time()
        }
        # ブラウザが購読しているトピック（仮: gui/control）へパブリッシュ
        self.client.publish("gui/control", json.dumps(ui_cmd))
        logger.info(f"🚀 UI Kick sent: Open panel for {vst_role}")

    # ---------------------------------------------------------
    # サブプロセス管理・実行
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
        threading.Thread(target=self.command_dispatcher_loop, daemon=True).start()

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