import paho.mqtt.client as mqtt
import json
import os
import sys
import subprocess
import time
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
        
        # 映像受信プロセスの管理用
        self.stream_process = None
        self.rx_script_path = os.path.join(current_dir, "wmp_stream_rx.py")

    def manage_stream_process(self, is_active):
        """wmp_stream_rx.py の起動と停止を管理"""
        if is_active:
            # プロセスが動いていない場合のみ起動
            if self.stream_process is None or self.stream_process.poll() is not None:
                print(f"🎬 Starting Stream Receiver: {self.rx_script_path}")
                self.stream_process = subprocess.Popen(
                    ["python3", self.rx_script_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT
                )
        else:
            # プロセスが動いていたら停止
            if self.stream_process and self.stream_process.poll() is None:
                print("🛑 Stopping Stream Receiver...")
                self.stream_process.terminate()
                try:
                    self.stream_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.stream_process.kill()
                self.stream_process = None

    def on_connect(self, client, userdata, flags, rc):
        print(f"🌐 Hub Manager Connected (Result code {rc})")
        client.subscribe("wildlink/+/res")

    def on_message(self, client, userdata, msg):
        try:
            topic_parts = msg.topic.split('/')
            node_id = topic_parts[1]
            payload = json.loads(msg.payload.decode())
            
            # 1. DB更新（ステータスや環境データ）
            self.db.update_node_status(node_id, payload)
            
            # 2. 映像ストリーム命令の成否をチェックしてプロセスを連動
            # payload["camera"]["act_stream"] があるか確認
            if "camera" in payload and "act_stream" in payload["camera"]:
                is_streaming = payload["camera"]["act_stream"]
                # コマンドが成功(success)または実行中(ack)の場合に連動
                if payload.get("val_status") in ["success", "ack"]:
                    self.manage_stream_process(is_streaming)
                elif not is_streaming:
                    # 明示的に false が来た場合も止める
                    self.manage_stream_process(False)

        except Exception as e:
            print(f"❌ Error in Hub on_message: {e}")

    def run(self):
        broker = os.getenv("MQTT_BROKER", "localhost")
        self.client.connect(broker, 1883, 60)
        print(f"📡 Hub Manager starting loop (Broker: {broker})...")
        try:
            self.client.loop_forever()
        except KeyboardInterrupt:
            self.manage_stream_process(False) # 終了時に受信機も殺す
            print("Hub Manager stopped.")

if __name__ == "__main__":
    manager = WildLinkHubManager()
    manager.run()