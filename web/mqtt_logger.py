import paho.mqtt.client as mqtt
import mysql.connector
import json
from datetime import datetime

# --- 設定 ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'watcher_user',
    'password': 'your_password', # 設定したパスワードに変更
    'database': 'field_watcher'
}

MQTT_BROKER = "localhost"
TOPIC_STATUS = "field/status/+"  # 遺言(LWT)や死活監視
TOPIC_SENSOR = "field/sensor/+"  # 気温、電圧など
TOPIC_LOGS   = "field/logs/+"    # エラーや動作ログ

# --- データベース操作関数 ---
def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def log_event(node_id, command, status, level, message):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO command_logs (node_id, command, status, level, message) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(sql, (node_id, command, status, level, message))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"[{datetime.now()}] EVENT: {node_id} - {message}")
    except Exception as e:
        print(f"DB Error (log_event): {e}")

def update_node_status(node_id, is_online, cpu_temp=None, volt=None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # 存在しなければ追加、あれば更新
        sql = """
        INSERT INTO node_status (node_id, is_online, last_seen, cpu_temp, battery_volt)
        VALUES (%s, %s, NOW(), %s, %s)
        ON DUPLICATE KEY UPDATE
        is_online=%s, last_seen=NOW(), 
        cpu_temp=IFNULL(%s, cpu_temp), 
        battery_volt=IFNULL(%s, battery_volt)
        """
        cursor.execute(sql, (node_id, is_online, cpu_temp, volt, is_online, cpu_temp, volt))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"DB Error (update_status): {e}")

# --- MQTT イベント ---
def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT Broker with result code {rc}")
    # 全ノードのステータス、センサー、ログを購読
    client.subscribe("field/#")

def on_message(client, userdata, msg):
    topic_parts = msg.topic.split('/')
    if len(topic_parts) < 3: return
    
    category = topic_parts[1] # status, sensor, logs
    node_id = topic_parts[2]  # cam1, node_02 など
    payload = msg.payload.decode()

    # 1. 死活監視・遺言(LWT)の処理
    if category == "status":
        if payload == "OFFLINE":
            update_node_status(node_id, 0)
            log_event(node_id, 'NETWORK', 'error', 'error', '通信断絶 (LWT検知)')
        elif payload == "ONLINE":
            update_node_status(node_id, 1)
            log_event(node_id, 'NETWORK', 'info', 'info', 'オンライン復帰')

    # 2. センサーデータの処理
    elif category == "sensor":
        try:
            data = json.loads(payload)
            # node_statusを更新
            update_node_status(node_id, 1, cpu_temp=data.get('temp'), volt=data.get('volt'))
            # sensor_logsに履歴を保存
            conn = get_db_connection()
            cursor = conn.cursor()
            for s_type, val in data.items():
                cursor.execute("INSERT INTO sensor_logs (node_id, sensor_type, val) VALUES (%s, %s, %s)", 
                               (node_id, s_type, val))
            conn.commit()
            cursor.close()
            conn.close()
        except json.JSONDecodeError:
            print(f"Invalid JSON from {node_id}")

    # 3. ログ・エラーの処理
    elif category == "logs":
        log_event(node_id, 'SYSTEM', 'info', 'info', payload)

# --- メイン処理 ---
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, 1883, 60)
client.loop_forever()