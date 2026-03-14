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

# ロガーの初期化 (log_type="hub_manager" として登録されます)
logger = get_logger("hub_manager")

class WildLinkHubManager:
    def __init__(self):
        self.db = DBBridge()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="wildlink_hub")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.stream_process = None
        self.rx_script_path = os.path.join(current_dir, "wmp_stream_rx.py")
        self.running = True

    def manage_stream_process(self, is_active):
        """RXプロセスの死活監視・管理"""
        if is_active:
            if self.stream_process is None or self.stream_process.poll() is not None:
                logger.info(f"🎬 Starting Stream Receiver: {self.rx_script_path}")
                self.stream_process = subprocess.Popen(
                    ["python3", self.rx_script_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT
                )
        else:
            if self.stream_process and self.stream_process.poll() is None:
                logger.info("🛑 Stopping Stream Receiver...")
                self.stream_process.terminate()
                try:
                    self.stream_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.stream_process.kill()
                self.stream_process = None

    def command_dispatcher_loop(self):
        """DBから pending コマンドを拾って送信する運び屋"""
        logger.info("📨 Command Dispatcher Loop is active.")
        while self.running:
            try:
                commands = self.db.fetch_pending_commands() 
                for cmd in commands:
                    cmd_id = cmd['id']
                    node_id = cmd['sys_id'] 
                    cmd_type = cmd.get('cmd_type', 'vst_control')
                    
                    topic = f"vst/{node_id}/cmd/{cmd_type}"
                    
                    try:
                        payload_dict = json.loads(cmd['cmd_json']) if cmd['cmd_json'] else {}
                    except:
                        payload_dict = {"raw": cmd['cmd_json']}
                    
                    payload_dict['cmd_id'] = cmd_id
                    json_payload = json.dumps(payload_dict)

                    # MQTTパブリッシュ
                    logger.info(f"📤 Dispatching [ID:{cmd_id}] to {topic}")
                    self.client.publish(topic, json_payload, qos=1)
                    
                    # 履歴を 'sent' に更新
                    self.db.update_command_status(cmd_id, "sent")
                    
            except Exception as e:
                logger.error(f"❌ Dispatcher Error: {e}")
            
            time.sleep(1)

    def on_connect(self, client, userdata, flags, rc):
        logger.info(f"🌐 Hub Manager Connected (rc:{rc})")
        client.subscribe("vst/+/res") 

    def on_message(self, client, userdata, msg):
        """Nodeからの実行結果を受け取った時の処理"""
        try:
            payload = json.loads(msg.payload.decode())
            logger.debug(f"📥 Received Response from Node: {payload}")

            # 1. 履歴の更新
            self.db.update_node_status(None, payload)
            
            # 2. 停止命令成功時の即時同期
            if payload.get('val_status') == 'success' and 'stop' in payload.get('cmd', ''):
                sys_id = payload.get('sys_id')
                vst_type = payload.get('vst_type')
                if sys_id and vst_type:
                    self.db.update_vst_status(sys_id, vst_type, "idle")
                    logger.info(f"✅ Immediate DB Sync: {vst_type} -> idle")

        except Exception as e:
            logger.error(f"❌ Message Handler Error: {e}")

    def run(self):
        self.manage_stream_process(True)

        broker = os.getenv("MQTT_BROKER", "localhost")
        self.client.connect(broker, 1883, 60)
        self.client.loop_start()
        
        dispatch_thread = threading.Thread(target=self.command_dispatcher_loop, daemon=True)
        dispatch_thread.start()

        logger.info(f"📡 Hub Manager is running...")
        try:
            while self.running:
                self.manage_stream_process(True)
                time.sleep(5)
        except KeyboardInterrupt:
            self.running = False
            self.manage_stream_process(False)
            self.client.loop_stop()

if __name__ == "__main__":
    manager = WildLinkHubManager()
    manager.run()