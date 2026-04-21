import paho.mqtt.client as mqtt
import json
import os
import sys
import subprocess
import time
import threading
from datetime import datetime

# --- フェーズ1: パス解決と.envの確実な読み込み ---
current_dir = os.path.dirname(os.path.abspath(__file__))
wildlink_root = os.path.dirname(current_dir) # プロジェクトのルート (wildlink/)

# .env を明示的に読み込む
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(wildlink_root, ".env"))
except ImportError:
    pass

# ルートディレクトリをパスに追加
if wildlink_root not in sys.path:
    sys.path.insert(0, wildlink_root)
common_path = os.path.join(wildlink_root, "common")
if common_path not in sys.path:
    sys.path.append(common_path)

# --- WildLink 共通モジュールのインポート ---
from common import config_loader  
from db_bridge import DBBridge
from logger_config import get_logger

logger = get_logger("hub_manager")
MQTT_PREFIX = getattr(config_loader, 'MQTT_PREFIX', 'wildlink')
GROUP_ID    = getattr(config_loader, 'GROUP_ID', 'home_internal')

class WildLinkHubManager:
    """
    WildLink Event Standard (WES) 2026 準拠
    役割: 全ノードのコマンド一元配送、ステータス同期、およびイベント中継（UI連携）。
    """
    def __init__(self):
        """初期化：DB接続、MQTTクライアントの準備、サブプロセスの定義を行います。"""
        self.db = DBBridge()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="wildlink_hub")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.processes = {
            "stream_rx": {"path": os.path.join(current_dir, "wmp_stream_rx.py"), "proc": None, "id": "hub_001"},
            "status_eng": {"path": os.path.join(current_dir, "status_engine.py"), "proc": None, "id": "hub_001"}
        }
        self.running = True

    def on_connect(self, client, userdata, flags, rc):
        """MQTTブローカー接続時のコールバック。UIやノードからのトピックを購読します。"""
        if rc == 0:
            logger.info("🌐 Hub Manager Connected Successfully.")
            client.subscribe("system/hub/kick")
            client.subscribe(f"{MQTT_PREFIX}/{GROUP_ID}/+/+/res")
            client.subscribe(f"{MQTT_PREFIX}/{GROUP_ID}/+/+/event")
        else:
            logger.error(f"❌ Connection failed with code {rc}")

    def on_message(self, client, userdata, msg):
        """MQTTメッセージ受信時のコールバック。受信内容をDBやUI、Nodeへ適切に振り分けます。"""
        try:
            if msg.topic == "system/hub/kick":
                logger.info("⚡ [HUB] Received kick from UI. Checking pending commands...")
                self._dispatch_pending_commands()
                return

            parts = msg.topic.split('/')
            if len(parts) < 5 or parts[0] != MQTT_PREFIX: 
                return
            
            sys_id   = parts[2]
            vst_role = parts[3]
            msg_type = parts[4]

            payload = json.loads(msg.payload.decode())
            if not isinstance(payload, dict): return

            # --- VSTからのレスポンス(res)処理 ---
            if msg_type == 'res':
                cmd_status = payload.get('cmd_status')
                val_status = payload.get('val_status')
                ref_id = payload.get('ref_cmd_id') or payload.get('cmd_id')
                log_ext = payload.get('log_ext') # フェーズ2: 拡張データの器を取得

                # 1. 現在のステータス(生存確認・稼働状態)を更新
                if val_status:
                    self.db.update_node_status(sys_id, vst_role, payload)

                # 2. コマンドのライフサイクル管理
                if ref_id and cmd_status:
                    self._handle_command_lifecycle(ref_id, cmd_status, payload)

                # 3. 【フェーズ2: 設定同期】の堅牢化
                # 設定変更が正常に完了し、かつ設定値(log_ext)が含まれている場合
                if cmd_status == 'completed' and log_ext:
                    # 🌟 救済措置: log_ext が文字列で届いた場合は辞書にパースする
                    if isinstance(log_ext, str):
                        try:
                            log_ext = json.loads(log_ext)
                        except Exception as e:
                            logger.error(f"⚠️ [Sync] Failed to parse log_ext string: {e}")
                            log_ext = None

                    # 辞書として確定している場合のみ同期実行
                    if isinstance(log_ext, dict):
                        logger.info(f"🔄 [Sync] '{vst_role}' reporting new config. Syncing...")
                        sync_success = self.db.update_vst_configs(sys_id, vst_role, log_ext)
                        if sync_success:
                            logger.info(f"✅ [Sync] node_configs synchronized successfully.")
                        else:
                            logger.warning(f"⚠️ [Sync] node_configs sync failed for {vst_role}.")
                    else:
                        logger.debug(f"ℹ️ [Sync] log_ext is empty or invalid format for {vst_role}.")

            # --- VSTからのイベント(event)処理 ---
            elif msg_type == 'event':
                event_name = payload.get('event')
                logger.info(f"📥 [event] {sys_id}:{vst_role} -> {event_name}")

                # 1. システムログへの記録 (常に実行)
                self.db.insert_event_log(sys_id, vst_role, payload)

                # --- 🌟 追加: 起動時（boot）の設定同期ロジック ---
                if event_name == "boot":
                    logger.info(f"🚀 [boot] Node {sys_id}:{vst_role} joined. Sending latest config...")
                    # DBから最新設定を取得
                    # fetch_node_config 等を使用して、このノード・役割の設定を抽出
                    node_configs = self.db.fetch_node_config(sys_id) 
                    
                    # 対象の vst_role に合致する設定を探して送信
                    for cfg in node_configs:
                        if cfg['vst_role_name'] == vst_role:
                            # 2026年仕様: act_ や val_ を含む cmd_json を作成
                            cmd_json = cfg.get('val_params', {})
                            # コマンドを発行 (target_role 宛に config_update を投げる)
                            self._send_command_to_node(sys_id, vst_role, "config_update", cmd_json)
                    return

                # 2. node_data (履歴) への記録
                # マニフェスト準拠: act_db (旧 save_db) が 1 (または True) なら記録する
                act_db = payload.get('act_db', payload.get('save_db', 0))
                
                if act_db == 1 or act_db is True:
                    success = self.db.insert_node_data(sys_id, vst_role, payload)
                    if success:
                        logger.info(f"💾 [DB] Node data saved to node_data for {vst_role}.")
                    else:
                        logger.error(f"❌ [DB] Failed to save node_data for {vst_role}.")

                # 3. UIのキック処理など
                if event_name in ["streaming_started", "stream_ready"]:
                    self._kick_ui_panel(sys_id, vst_role, payload)

        except Exception as e:
            logger.error(f"❌ Message Handler Error: {e}")

    def _dispatch_pending_commands(self):
        """DB上の未送信コマンド(pending)を抽出し、対象ノードのMQTTトピックへ配送します。"""
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
                
                payload['cmd_id'] = cmd_id
                json_payload = json.dumps(payload, ensure_ascii=False)
                
                logger.info(f"📤 Dispatching [ID:{cmd_id}] to {topic}")
                
                self.client.publish(topic, json_payload, qos=1)
                self.db.update_command_status(cmd_id, "sent")
                
        except Exception as e:
            logger.error(f"❌ Dispatcher Error: {e}")

    def _send_command_to_node(self, sys_id, role, action, params):
        topic = f"{MQTT_PREFIX}/{GROUP_ID}/{sys_id}/{role}/cmd"
        
        # 基本のペイロード
        payload = {"action": action, "cmd_id": 0}
        
        # 🌟 params（辞書）の中身を payload 直下に展開（平坦化）する
        if isinstance(params, dict):
            payload.update(params)
            
        # ※ Hub側はPaho-MQTTを直接叩いているため json.dumps が必要です
        self.client.publish(topic, json.dumps(payload, ensure_ascii=False))

    def _handle_command_lifecycle(self, cmd_id, status, payload):
        """コマンドの進行状況(ACK, 完了, エラー)を判定し、DBのステータスを更新します。"""
        if status == "acknowledged":
            logger.info(f"✅ [ACK] Command {cmd_id} acknowledged by node.")
            self.db.mark_command_acknowledged(cmd_id)
        
        elif status == "completed" or status == "success":
            logger.info(f"🏁 [FIN] Command {cmd_id} completed successfully.")
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
        
        elif status in ["failed", "error"]:
            logger.error(f"⚠️ [ERR] Command {cmd_id} failed reported by node.")
            self.db.finalize_command(
                cmd_id=cmd_id,
                status="error",
                log_msg=payload.get('log_msg', 'Failed/Error reported'),
                log_code=payload.get('log_code', 500),
                res_payload=payload
            )

    def _kick_ui_panel(self, sys_id, vst_role, payload):
        """UIに対して、特定のパネルを開くなどの制御コマンドをMQTT経由で送信します。"""
        ui_cmd = {
            "action": "open_panel",
            "target_role": vst_role,
            "net_port": payload.get("net_port"),
            "timestamp": time.time()
        }
        self.client.publish("gui/control", json.dumps(ui_cmd))
        logger.info(f"🚀 UI Kick sent: Open panel for {vst_role}")

    def _spawn_process(self, name):
        """個別のサブプロセスを起動します。環境変数(PYTHONPATH)を保護し、モジュールを見失わないようにします。"""
        conf = self.processes[name]
        env = os.environ.copy()
        env["SYS_ID"] = conf["id"]
        # フェーズ1: サブプロセスの環境変数にプロジェクトルートを追加して保護
        env["PYTHONPATH"] = wildlink_root
        
        logger.info(f"🎬 Starting {name}: {conf['path']}")
        return subprocess.Popen(
            ["python3", conf["path"]],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            cwd=wildlink_root 
        )

    def manage_sub_processes(self, should_run):
        """定義されたサブプロセス群の起動・停止状態を一元管理します。"""
        for name, info in self.processes.items():
            if should_run:
                if info["proc"] is None or info["proc"].poll() is not None:
                    info["proc"] = self._spawn_process(name)
            else:
                if info["proc"] and info["proc"].poll() is None:
                    info["proc"].terminate()
                    info["proc"] = None

    def run(self):
        """Hubのメインループ。MQTT接続を維持し、サブプロセスの死活監視を行います。"""
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
            # 安全な終了処理の担保
            logger.info("🛑 Keyboard interrupt received. Shutting down Hub Manager...")
        finally:
            self.running = False
            self.manage_sub_processes(False)
            self.client.loop_stop()
            self.client.disconnect()

if __name__ == "__main__":
    if not os.getenv("SYS_ID"):
        os.environ["SYS_ID"] = "hub_001"
    WildLinkHubManager().run()