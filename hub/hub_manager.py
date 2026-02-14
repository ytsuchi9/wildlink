import paho.mqtt.client as mqtt
import mysql.connector
import json
import os
from dotenv import load_dotenv

# プロジェクトのルートにある .env を絶対パスで直接指定する
# あなたの環境に合わせて '/opt/wildlink/.env' などに書き換えてください
DOTENV_PATH = '/opt/wildlink/.env' 

if os.path.exists(DOTENV_PATH):
    load_dotenv(DOTENV_PATH)
    print(f"✅ Loaded .env from {DOTENV_PATH}")
else:
    print(f"❌ Could not find .env at {DOTENV_PATH}")

# デバッグ表示（これで None が出ないことを確認！）
print(f"DEBUG: DB_USER is [{os.getenv('DB_USER')}]")

DB_CONFIG = {
    'host': '127.0.0.1', # 自分自身
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASS'),
    'database': os.getenv('DB_NAME')
}

def save_to_db(node_id, data):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 振り分けロジック
        env_data = {k: v for k, v in data.items() if k.startswith('env_')}
        sys_data = {k: v for k, v in data.items() if k.startswith('sys_') or k.startswith('net_')}

        if env_data:
            sql = "INSERT INTO sensor_logs (sys_id, env_temp, env_hum, raw_data) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (node_id, env_data.get('env_temp'), env_data.get('env_hum'), json.dumps(data)))

        if sys_data:
            sql = "INSERT INTO system_logs (sys_id, sys_volt, sys_cpu_t, net_rssi, log_msg) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(sql, (node_id, sys_data.get('sys_volt'), sys_data.get('sys_cpu_t'), sys_data.get('net_rssi'), sys_data.get('log_msg')))

        cursor.execute("UPDATE nodes SET last_seen = CURRENT_TIMESTAMP WHERE sys_id = %s", (node_id,))
        conn.commit()
        conn.close()
        print(f"[*] DB Updated: {node_id}")
    except Exception as e:
        print(f"[!] DB Error: {e}")

def on_message(client, userdata, msg):
    try:
        node_id = msg.topic.split('/')[1]
        payload = json.loads(msg.payload.decode())
        for unit_name, unit_data in payload.items():
            save_to_db(node_id, unit_data)
    except Exception as e:
        print(f"Error: {e}")

client = mqtt.Client()
client.on_message = on_message
client.connect("127.0.0.1", 1883, 60) # 自分自身のブローカーへ
client.subscribe("wildlink/+/res")
print("👂 Hub Manager listening...")
client.loop_forever()