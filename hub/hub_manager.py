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

# ロガーの初期化
logger = get_logger("hub_manager")

class WildLinkHubManager:
    def __init__(self):
        self.db = DBBridge()
        # 最新のAPIバージョンを使用
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="wildlink_hub")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.processes = {
            "stream_rx": {"path": os.path.join(current_dir, "wmp_stream_rx.py"), "proc": None, "id": "hub_001"},
            "status_eng": {"path": os.path.join(current_dir, "status_engine.py"), "proc": None, "id": "hub_001"}
        }
        self.running = True

    def _spawn_process(self, name):
        """個別の環境変数(SYS_ID)を注入して子プロセスを起動"""
        conf = self.processes[name]
        script_path = conf["path"]
        sys_id = conf["id"] # DB上の sys_id と一致させる

        if not os.path.exists(script_path):
            logger.error(f"⚠️ Script not found: {script_path}")
            return

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
        """
        DBからの予約コマンド（スケジュール実行など）を拾うループ。
        send_cmd.php (Web) を通らないコマンドのバックアップとして機能。
        """
        logger.info("📨 Command Dispatcher Loop is active.")
        while self.running:
            try:
                commands = self.db.fetch_pending_commands() 
                for cmd in commands:
                    cmd_id = cmd['id']
                    target_sys = cmd['sys_id'] 
                    # WES 2026: DBのカラム名に合わせた取得 (vst_role_name)
                    role_name = cmd.get('vst_role_name', 'system') 
                    
                    # 💡 WES 2026 トピック形式: nodes/{sys_id}/{role}/cmd
                    topic = f"nodes/{target_sys}/{role_name}/cmd"
                    
                    try:
                        payload_dict = json.loads(cmd['cmd_json']) if cmd['cmd_json'] else {}
                    except:
                        payload_dict = {"raw_payload": cmd['cmd_json']}
                    
                    payload_dict['cmd_id'] = cmd_id
                    payload_dict['role'] = role_name
                    
                    json_payload = json.dumps(payload_dict)
                    logger.info(f"📤 Dispatching [ID:{cmd_id}] to {topic}")
                    self.client.publish(topic, json_payload, qos=1)
                    
                    self.db.update_command_status(cmd_id, "sent")
                    
            except Exception as e:
                logger.error(f"❌ Dispatcher Error: {e}")
            
            time.sleep(1)

    def on_connect(self, client, userdata, flags, rc):
        logger.info(f"🌐 Hub Manager Connected (rc:{rc})")
        # 💡 WES 2026 階層: 全ノードの応答(res)と通知(event)をまとめて監視
        client.subscribe("nodes/+/+/res")
        client.subscribe("nodes/+/+/event")
        # ハブ自身(hub_001)への直接命令も監視
        client.subscribe(f"nodes/{os.getenv('SYS_ID')}/+/cmd")

    def on_message(self, client, userdata, msg):
        """
        Nodeからの JSON パッチを受け取り、DBの状態を「部分更新」する
        """
        try:
            # トピック解析 (例: nodes/node_001/cam_main/res)
            parts = msg.topic.split('/')
            if len(parts) < 4: return
            
            sys_id = parts[1]
            role   = parts[2]
            msg_type = parts[3] # res, event, cmd
            
            payload = json.loads(msg.payload.decode())
            logger.info(f"📥 [{msg_type}] from [{sys_id}:{role}] status:{payload.get('val_status')}")

            # 1. 最新ステータスの書き戻し (DBBridge.update_node_status)
            # WES 2026コンセプト: 届いた payload (JSON) をそのまま raw_data カラムへ
            self.db.update_node_status(sys_id, role, payload)
            
            # 2. コマンド完了通知の場合、履歴テーブルのステータスを更新
            if msg_type == 'res' and 'cmd_id' in payload:
                self.db.update_command_status(payload['cmd_id'], payload.get('val_status', 'success'))

            # 3. イベント（動体検知など）の場合は、専用ログテーブルにも挿入
            if msg_type == 'event':
                self.db.insert_event_log(sys_id, role, payload)

        except Exception as e:
            logger.error(f"❌ Message Handler Error: {e}")

    def run(self):
        self.manage_sub_processes(True)
        broker = os.getenv("MQTT_BROKER", "localhost")
        self.client.connect(broker, 1883, 60)
        self.client.loop_start()
        
        dispatch_thread = threading.Thread(target=self.command_dispatcher_loop, daemon=True)
        dispatch_thread.start()

        logger.info(f"📡 Hub Manager is running...")
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
        os.environ["SYS_ID"] = "hub_001" # ハブ自体のIDを固定
    
    manager = WildLinkHubManager()
    manager.run()