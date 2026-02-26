import paho.mqtt.client as mqtt
import json
import os
import sys
import subprocess
import time
import threading  # 追加
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
        # 最新のPaho MQTTライブラリに対応
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="wildlink_hub")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.stream_process = None
        self.rx_script_path = os.path.join(current_dir, "wmp_stream_rx.py")
        
        # コマンド送信ループの停止フラグ
        self.running = True

    def manage_stream_process(self, is_active):
        """wmp_stream_rx.py の起動と停止を管理"""
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
        """DBから未処理コマンドを探してMQTTで送るループ (別スレッド)"""
        print("📨 Command Dispatcher started.")
        while self.running:
            try:
                # 1. DBから 'pending' ステータスのコマンドを取得
                commands = self.db.fetch_pending_commands() 
                
                for cmd in commands:
                    # 【重要】DBのカラム名に合わせて 'sys_id' を使用
                    node_id = cmd['sys_id'] 
                    topic = f"node/cmd/{node_id}"
                    
                    # cmd_json が文字列で保存されている場合のパース処理（念のため）
                    params = {}
                    if 'cmd_json' in cmd and cmd['cmd_json']:
                        try:
                            params = json.loads(cmd['cmd_json']) if isinstance(cmd['cmd_json'], str) else cmd['cmd_json']
                        except:
                            pass

                    payload = {
                        "target": params.get("target", "manager"),
                        "action": params.get("action", "reload"),
                        "cmd_id": cmd['id']
                    }
                    
                    # 2. MQTTパブリッシュ
                    print(f"📤 Sending command to {node_id}: {payload['action']} (ID: {cmd['id']})")
                    self.client.publish(topic, json.dumps(payload), qos=1)
                    
                    # 3. ステータスを 'sent' に更新
                    self.db.update_command_status(cmd['id'], "sent")
                    
            except Exception as e:
                # ここでエラー内容を詳しく出すようにするとデバッグが捗ります
                print(f"❌ Error in command_dispatcher: {e}")
            
            time.sleep(2)

    def on_connect(self, client, userdata, flags, rc):
        print(f"🌐 Hub Manager Connected (Result code {rc})")
        # Nodeからの応答トピックを購読
        client.subscribe("node/status/+") # センサーデータなど
        client.subscribe("wildlink/+/res") # 実行結果など

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            # トピックからNode IDを特定 (例: node/status/node_001)
            topic_parts = msg.topic.split('/')
            node_id = topic_parts[-1] 

            # ステータス更新
            self.db.update_node_status(node_id, payload)
            
            # ストリーム連動ロジック (既存)
            if "camera" in payload and "act_stream" in payload["camera"]:
                is_streaming = payload["camera"]["act_stream"]
                if payload.get("val_status") in ["success", "ack"]:
                    self.manage_stream_process(is_streaming)
                elif not is_streaming:
                    self.manage_stream_process(False)

        except Exception as e:
            print(f"❌ Error in Hub on_message: {e}")

    def run(self):
        broker = os.getenv("MQTT_BROKER", "localhost")
        self.client.connect(broker, 1883, 60)
        
        # MQTTループをバックグラウンドで開始
        self.client.loop_start()
        
        # コマンド配送ループを別スレッドで開始
        dispatch_thread = threading.Thread(target=self.command_dispatcher_loop)
        dispatch_thread.start()

        print(f"📡 Hub Manager is running (Broker: {broker})...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopping Hub Manager...")
            self.running = False
            self.manage_stream_process(False)
            self.client.loop_stop()
            dispatch_thread.join()

if __name__ == "__main__":
    manager = WildLinkHubManager()
    manager.run()