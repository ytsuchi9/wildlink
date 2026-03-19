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
        # 2026年仕様: 最新のCallback APIを使用
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="wildlink_hub")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # 子プロセス管理用
        self.processes = {
            # Receiver は hub_001 として振る舞う
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
        """DBから pending コマンドを拾って送信する運び屋"""
        logger.info("📨 Command Dispatcher Loop is active.")
        while self.running:
            try:
                # DBBridge.fetch_pending_commands() が 
                # SELECT * FROM node_commands WHERE val_status='pending' 
                # を実行することを前提としています
                commands = self.db.fetch_pending_commands() 
                for cmd in commands:
                    cmd_id = cmd['id']
                    target_sys = cmd['sys_id'] 
                    role_name = cmd.get('vst_role_name', 'default') # DBのカラムから直接取得
                    cmd_type = cmd.get('cmd_type', 'vst_control')
                    
                    # 宛先トピック: vst/{node_001}/cmd/vst_control
                    topic = f"vst/{target_sys}/cmd/{cmd_type}"
                    
                    try:
                        payload_dict = json.loads(cmd['cmd_json']) if cmd['cmd_json'] else {}
                    except:
                        payload_dict = {"raw": cmd['cmd_json']}
                    
                    # 2026年仕様: ペイロードの正規化
                    payload_dict['sys_id'] = target_sys
                    payload_dict['cmd_id'] = cmd_id
                    payload_dict['role'] = role_name # 実行対象を明示
                    
                    json_payload = json.dumps(payload_dict)

                    logger.info(f"📤 Dispatching [ID:{cmd_id}] Role:{role_name} to {topic}")
                    self.client.publish(topic, json_payload, qos=1)
                    
                    # DB側のステータスを "sent" に更新
                    self.db.update_command_status(cmd_id, "sent")
                    
            except Exception as e:
                logger.error(f"❌ Dispatcher Error: {e}")
            
            time.sleep(1)

    def on_connect(self, client, userdata, flags, rc):
        logger.info(f"🌐 Hub Manager Connected (rc:{rc})")
        # ノードからの実行結果(res)と、ハブ自身への命令(cmd)を両方監視
        client.subscribe("vst/+/res") 
        client.subscribe(f"vst/{os.getenv('SYS_ID')}/cmd/+")

    def on_message(self, client, userdata, msg):
        """Nodeからの実行結果(res)を受け取りDBを更新"""
        try:
            payload = json.loads(msg.payload.decode())
            sys_id = payload.get('sys_id')
            role = payload.get('role', 'unknown')
            status = payload.get('val_status', 'unknown')
            
            logger.info(f"📥 Response from [{sys_id}] Role:[{role}] -> {status}")
            
            # DBの node_status_current を更新
            # DBBridge側で「vst_role_name」に基づいたUPDATEが走るように実装してください
            self.db.update_node_status(sys_id, payload)
            
            # もし cmd_id が含まれていれば、node_commands の最終ステータスも success にする
            if 'cmd_id' in payload:
                self.db.update_command_status(payload['cmd_id'], status)

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