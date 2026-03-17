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
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="wildlink_hub")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # 子プロセス管理用
        self.processes = {
            "stream_rx": {"path": os.path.join(current_dir, "wmp_stream_rx.py"), "proc": None, "id": "hub_rx_01"},
            "status_eng": {"path": os.path.join(current_dir, "status_engine.py"), "proc": None, "id": "hub_stat_01"}
        }
        
        self.running = True

    def _spawn_process(self, name):
        """個別の環境変数(SYS_ID)を注入して子プロセスを起動"""
        conf = self.processes[name]
        script_path = conf["path"]
        role_id = conf["id"]

        if not os.path.exists(script_path):
            logger.error(f"⚠️ Script not found: {script_path}")
            return

        # 環境変数の準備
        env = os.environ.copy()
        env["SYS_ID"] = role_id  # 💡 Role-Based IDを注入！

        logger.info(f"🎬 Starting {name} as [{role_id}]: {script_path}")
        return subprocess.Popen(
            ["python3", script_path],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            cwd=wildlink_root  # ルートを作業ディレクトリに設定
        )

    def manage_sub_processes(self, should_run):
        """全サブプロセスの死活監視・管理"""
        for name in self.processes:
            proc_info = self.processes[name]
            
            if should_run:
                # 起動していない、または落ちている場合に再起動
                if proc_info["proc"] is None or proc_info["proc"].poll() is not None:
                    proc_info["proc"] = self._spawn_process(name)
            else:
                # 停止処理
                if proc_info["proc"] and proc_info["proc"].poll() is None:
                    logger.info(f"🛑 Stopping {name}...")
                    proc_info["proc"].terminate()
                    try:
                        proc_info["proc"].wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc_info["proc"].kill()
                    proc_info["proc"] = None

    def command_dispatcher_loop(self):
        """DBから pending コマンドを拾って送信する運び屋"""
        logger.info("📨 Command Dispatcher Loop is active.")
        while self.running:
            try:
                commands = self.db.fetch_pending_commands() 
                for cmd in commands:
                    cmd_id = cmd['id']
                    sys_id = cmd['sys_id'] 
                    cmd_type = cmd.get('cmd_type', 'vst_control')
                    
                    topic = f"vst/{sys_id}/cmd/{cmd_type}"
                    
                    try:
                        payload_dict = json.loads(cmd['cmd_json']) if cmd['cmd_json'] else {}
                    except:
                        payload_dict = {"raw": cmd['cmd_json']}
                    
                    payload_dict['sys_id'] = sys_id
                    payload_dict['cmd_id'] = cmd_id
                    json_payload = json.dumps(payload_dict)

                    logger.info(f"📤 Dispatching [ID:{cmd_id}] to {topic}")
                    self.client.publish(topic, json_payload, qos=1)
                    self.db.update_command_status(cmd_id, "sent")
                    
            except Exception as e:
                logger.error(f"❌ Dispatcher Error: {e}")
            
            time.sleep(1)

    def on_connect(self, client, userdata, flags, rc):
        logger.info(f"🌐 Hub Manager Connected (rc:{rc})")
        client.subscribe("vst/+/res") 

    def on_message(self, client, userdata, msg):
        """Nodeからの実行結果(res)を受け取った時の処理"""
        try:
            payload = json.loads(msg.payload.decode())
            sys_id = payload.get('sys_id')
            logger.debug(f"📥 Received Response from Node [{sys_id}]: {payload}")
            self.db.update_node_status(sys_id, payload)
        except Exception as e:
            logger.error(f"❌ Message Handler Error: {e}")

    def run(self):
        # 起動時にサブプロセス群を立ち上げ
        self.manage_sub_processes(True)

        broker = os.getenv("MQTT_BROKER", "localhost")
        self.client.connect(broker, 1883, 60)
        self.client.loop_start()
        
        dispatch_thread = threading.Thread(target=self.command_dispatcher_loop, daemon=True)
        dispatch_thread.start()

        logger.info(f"📡 Hub Manager is running...")
        try:
            while self.running:
                # 5秒おきにサブプロセスが生きているかチェック
                self.manage_sub_processes(True)
                time.sleep(5)
        except KeyboardInterrupt:
            self.running = False
            self.manage_sub_processes(False)
            self.client.loop_stop()

if __name__ == "__main__":
    # ハブマネージャー自身の SYS_ID は環境変数から（なければ hub_mgr_01）
    if not os.getenv("SYS_ID"):
        os.environ["SYS_ID"] = "hub_mgr_01"
    
    manager = WildLinkHubManager()
    manager.run()