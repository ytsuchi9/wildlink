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

# .envファイルの読み込みサポート
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(wildlink_root, ".env"))
except ImportError:
    pass

from db_bridge import DBBridge
from logger_config import get_logger

# ロガーの初期化
logger = get_logger("hub_manager")

class WildLinkHubManager:
    def __init__(self):
        self.db = DBBridge()
        # MQTTクライアント初期化 (WES 2026: Callback API v1)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="wildlink_hub")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # サブプロセスの定義
        self.processes = {
            "stream_rx": {"path": os.path.join(current_dir, "wmp_stream_rx.py"), "proc": None, "id": "hub_001"},
            "status_eng": {"path": os.path.join(current_dir, "status_engine.py"), "proc": None, "id": "hub_001"}
        }
        self.running = True

    def _spawn_process(self, name):
        """個別の環境変数(SYS_ID)を注入して子プロセスを起動"""
        conf = self.processes[name]
        script_path = conf["path"]
        sys_id = conf["id"]

        if not os.path.exists(script_path):
            logger.error(f"⚠️ Script not found: {script_path}")
            return None

        env = os.environ.copy()
        env["SYS_ID"] = sys_id 

        logger.info(f"🎬 Starting {name} for [{sys_id}]: {script_path}")
        return subprocess.Popen(
            ["python3", script_path],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            cwd=wildlink_root 
        )

    def manage_sub_processes(self, should_run):
        """全サブプロセスの死活監視・管理"""
        for name in self.processes:
            proc_info = self.processes[name]
            if should_run:
                if proc_info["proc"] is None or proc_info["proc"].poll() is not None:
                    proc_info["proc"] = self._spawn_process(name)
            else:
                if proc_info["proc"] and proc_info["proc"].poll() is None:
                    logger.info(f"🛑 Stopping {name}...")
                    proc_info["proc"].terminate()
                    try:
                        proc_info["proc"].wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc_info["proc"].kill()
                    proc_info["proc"] = None

    def command_dispatcher_loop(self):
        """DBからの予約コマンドを拾うループ"""
        logger.info("📨 Command Dispatcher Loop is active.")
        while self.running:
            try:
                commands = self.db.fetch_pending_commands() 
                for cmd in commands:
                    cmd_id = cmd['id']
                    target_sys = cmd['sys_id'] 
                    role_name = cmd.get('vst_role_name') or 'system' 
                    
                    topic = f"nodes/{target_sys}/{role_name}/cmd"
                    
                    try:
                        payload_dict = json.loads(cmd['cmd_json']) if cmd['cmd_json'] else {}
                    except:
                        payload_dict = {"raw_payload": cmd['cmd_json']}
                    
                    payload_dict['cmd_id'] = cmd_id
                    payload_dict['role'] = role_name
                    
                    json_payload = json.dumps(payload_dict, ensure_ascii=False)
                    logger.info(f"📤 Dispatching [ID:{cmd_id}] to {topic}")
                    
                    self.client.publish(topic, json_payload, qos=1)
                    self.db.update_command_status(cmd_id, "sent")
                    
            except Exception as e:
                logger.error(f"❌ Dispatcher Error: {e}")
            time.sleep(1)

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("🌐 Hub Manager Connected Successfully.")
            client.subscribe("nodes/+/+/res")
            client.subscribe("nodes/+/+/event")
            hub_id = os.getenv("SYS_ID", "hub_001")
            client.subscribe(f"nodes/{hub_id}/+/cmd")
        else:
            logger.error(f"❌ Connection failed with code {rc}")

    def on_message(self, client, userdata, msg):
        """
        WES 2026: 受信メッセージ解析
        修正: event メッセージでの status 更新を回避
        """
        try:
            parts = msg.topic.split('/')
            if len(parts) < 4: return
            
            sys_id   = parts[1]
            role     = parts[2]
            msg_type = parts[3] # res, event, cmd
            
            if role == "None" or sys_id == "None":
                return

            # ペイロードのデコードとJSONパース
            raw_payload = msg.payload.decode()
            try:
                payload = json.loads(raw_payload)
                if isinstance(payload, str):
                    payload = json.loads(payload)
            except json.JSONDecodeError:
                logger.error(f"❌ JSON Decode Error from {msg.topic}: {raw_payload}")
                return

            if not isinstance(payload, dict):
                logger.error(f"❌ Payload is not a dictionary: {type(payload)} from {msg.topic}")
                return

            status = payload.get('val_status', 'unknown')
            logger.info(f"📥 [{msg_type}] from [{sys_id}:{role}] status:{status}")

            # 1. node_configs / node_status_current の更新
            # WES 2026 修正: event 発生時はステータス上書きを避けるため res の場合のみステータスを更新する
            if msg_type == 'res':
                self.db.update_node_status(sys_id, role, payload)
            
            # 2. コマンド履歴(node_commands)の更新
            ref_id = payload.get('cmd_id') or payload.get('ref_cmd_id')
            
            if ref_id:
                # ノードからの最初の応答(acknowledged)で acked_at を打つ
                if status == "acknowledged":
                    logger.info(f"🕒 Marking Command [ID:{ref_id}] as Acknowledged")
                    self.db.mark_command_acknowledged(ref_id)
                
                # 完了報告 (success, error, streaming, idle等)
                elif msg_type == 'res':
                    logger.info(f"✅ Finalizing Command [ID:{ref_id}] as {status}")
                    self.db.finalize_command(
                        cmd_id=ref_id,
                        status=status,
                        log_msg=payload.get('log_msg', ''),
                        log_code=payload.get('log_code', 200),
                        res_payload=payload
                    )

            # 3. イベントログ保存 (全ての event はログに残す)
            if msg_type == 'event':
                self.db.insert_event_log(sys_id, role, payload)

        except Exception as e:
            logger.error(f"❌ Message Handler Error: {e}")

    def run(self):
        self.manage_sub_processes(True)
        broker = os.getenv("MQTT_BROKER", "localhost")
        try:
            self.client.connect(broker, 1883, 60)
        except Exception as e:
            logger.error(f"❌ Failed to connect to MQTT Broker: {e}")
            return

        self.client.loop_start()
        dispatch_thread = threading.Thread(target=self.command_dispatcher_loop, daemon=True)
        dispatch_thread.start()

        logger.info(f"📡 Hub Manager is running (SYS_ID: {os.getenv('SYS_ID')})")
        
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
    manager = WildLinkHubManager()
    manager.run()