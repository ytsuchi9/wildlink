import paho.mqtt.client as mqtt
import mysql.connector
import json

# --- 設定 ---
MQTT_BROKER = "127.0.0.1"
MQTT_TOPIC = "wildlink/+/data"
DB_CONFIG = {
    "host": "localhost",
    "user": "root",      # 環境に合わせて変更してください
    "password": "rootRoot",  # 環境に合わせて変更してください
    "database": "wildlink_db"
}

def save_to_db(payload):
    try:
        # 1. 届いた生データをデコード
        raw_str = payload.decode('utf-8')
        data = json.loads(raw_str)
        
        db = mysql.connector.connect(**DB_CONFIG)
        cursor = db.cursor()

        # 2. カラム一覧を取得
        cursor.execute("SHOW COLUMNS FROM node_data")
        columns = [column[0] for column in cursor.fetchall()]

        # 3. 辞書を作成（JSONにあるキー ∩ DBにあるカラム）
        valid_data = {k: v for k, v in data.items() if k in columns}

        # 4. 重要：raw_dataカラムに生のJSON文字列をセットする
        if "raw_data" in columns:
            valid_data["raw_data"] = raw_str

        if valid_data:
            cols = ", ".join(valid_data.keys())
            placeholders = ", ".join(["%s"] * len(valid_data))
            sql = f"INSERT INTO node_data ({cols}) VALUES ({placeholders})"
            
            cursor.execute(sql, list(valid_data.values()))
            db.commit()
            print(f"Stored with JSON: {valid_data.get('sys_node_id')}")
        
        cursor.close()
        db.close()
    except Exception as e:
        print(f"DB Error: {e}")

def on_message(client, userdata, msg):
    print(f"Received: {msg.topic}")
    save_to_db(msg.payload)

# MQTT Client Setup
# ※最新版 paho-mqtt 2.0+ の場合は CallbackAPIVersion が必要
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "db_logger")
client.on_message = on_message
client.connect(MQTT_BROKER, 1883, 60)
client.subscribe(MQTT_TOPIC)

print("Waiting for data...")
client.loop_forever()