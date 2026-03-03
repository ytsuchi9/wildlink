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
        if is_active:
            if self.stream_process is None or self.stream_process.poll() is not None:
                print(f"🎬 Starting Stream Receiver: {self.rx_script_path}")
                self.stream_process = subprocess.Popen(
                    ["python3", self.rx_script_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT
                )
        else:
            if self.stream_process and self.stream_process.poll() is None:
                print("🛑 Stopping Stream Receiver...")
                self.stream_process.terminate()
                try:
                    self.stream_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.stream_process.kill()
                self.stream_process = None

    def command_dispatcher_loop(self):
        """DBから pending コマンドを拾って送信する運び屋"""
        print("📨 Command Dispatcher Loop is active.")
        while self.running:
            try:
                # DBから 'pending' 状態のコマンドを取得
                commands = self.db.fetch_pending_commands() 
                
                for cmd in commands:
                    cmd_id = cmd['id']
                    node_id = cmd['sys_id'] 
                    cmd_type = cmd.get('cmd_type', 'vst_control') # PHP側と合わせる
                    
                    # 設計した新トピック形式: vst/node_001/cmd/vst_control
                    topic = f"vst/{node_id}/cmd/{cmd_type}"
                    
                    # cmd_json (パッチ) をパースして ID を付与
                    payload_dict = {}
                    if cmd['cmd_json']:
                        try:
                            payload_dict = json.loads(cmd['cmd_json'])
                        except:
                            payload_dict = {"raw": cmd['cmd_json']}
                    
                    # Node側にこのIDを返してもらうことで追跡を完結させる
                    payload_dict['cmd_id'] = cmd_id
                    
                    json_payload = json.dumps(payload_dict)

                    # MQTTパブリッシュ
                    print(f"📤 Dispatching [ID:{cmd_id}] to {topic} -> {json_payload}")
                    self.client.publish(topic, json_payload, qos=1)
                    
                    # ステータスを 'sent' に更新 (ここで WebUI のボタンが水色に変わる)
                    self.db.update_command_status(cmd_id, "sent")
                    
            except Exception as e:
                print(f"❌ Dispatcher Error: {e}")
            
            time.sleep(1) # 1秒周期

    def on_connect(self, client, userdata, flags, rc):
        print(f"🌐 Hub Manager Connected (rc:{rc})")
        # Nodeからの応答トピックを購読 (設計に合わせたワイルドカード)
        client.subscribe("vst/+/res") 

    def on_message(self, client, userdata, msg):
        """Nodeからの実行結果 (vst/node_001/res) を受け取った時の処理"""
        try:
            payload = json.loads(msg.payload.decode())
            # 実行結果をDBに反映 (acked_at や completed_at が更新される)
            self.db.update_node_status(None, payload) # node_idはpayload内から取得される
            print(f"📥 Received Response from Node: {payload}")
        except Exception as e:
            print(f"❌ Message Handler Error: {e}")

    def run(self):
        broker = os.getenv("MQTT_BROKER", "localhost")
        self.client.connect(broker, 1883, 60)
        self.client.loop_start()
        
        # Dispatcherを別スレッドで開始
        dispatch_thread = threading.Thread(target=self.command_dispatcher_loop, daemon=True)
        dispatch_thread.start()

        print(f"📡 Hub Manager is running...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False
            self.client.loop_stop()

if __name__ == "__main__":
    manager = WildLinkHubManager()
    manager.run()