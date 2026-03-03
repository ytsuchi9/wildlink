import sys
import os
import time
import json

# DBBridgeなどを読み込めるようにパスを通す
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common'))
from mqtt_client import MQTTClient
from db_bridge import DBBridge

# 設定
BROKER = "localhost"
db = DBBridge()

def on_message(client, userdata, msg):
    try:
        topic_parts = msg.topic.split('/')
        if len(topic_parts) < 3 or topic_parts[2] != "report":
            return

        node_id = topic_parts[1]
        payload = json.loads(msg.payload.decode())
        
        # SQLを理想の形（net_rssiあり）にする
        sql = """
            INSERT INTO node_data (sys_id, sys_cpu_t, net_rssi, raw_data)
            VALUES (%s, %s, %s, %s)
        """
        
        # JSONから値を取得
        sys_mon = payload.get("sys_monitor", {})
        cpu_t = sys_mon.get("sys_cpu_t", 0.0)
        rssi = sys_mon.get("net_rssi", -50.0)  # ここで取得
        raw_json = json.dumps(payload)
        
        # 実行
        db._execute(sql, (node_id, cpu_t, rssi, raw_json))
        print(f"[{node_id}] 📥 Report archived with RSSI: {rssi}")

    except Exception as e:
        print(f"❌ Status Engine Error: {e}")

# メイン起動
mqtt = MQTTClient(BROKER, "hub_status_engine")
mqtt.client.on_message = on_message
if mqtt.connect():
    # 2026年仕様のレポートトピックを購読
    mqtt.client.subscribe("vst/+/report")
    print("🚀 WildLink 2026 Status Engine started...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        mqtt.disconnect()