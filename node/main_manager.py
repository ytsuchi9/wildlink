import sys
import os
import time
import json
import importlib
import paho.mqtt.client as mqtt
import mysql.connector
from dotenv import load_dotenv

# --- パス解決 & 環境変数 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
wildlink_root = os.path.dirname(current_dir)
sys.path.append(os.path.join(wildlink_root, "common"))
sys.path.append(current_dir)

load_dotenv(os.path.join(wildlink_root, ".env"))

NODE_ID = os.getenv('NODE_ID', 'node_001')
MQTT_HOST = os.getenv('MQTT_BROKER') # Pi 2 の IP

DB_CONFIG = {
    'host': MQTT_HOST, 
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASS'),
    'database': os.getenv('DB_NAME')
}

TOPIC_CMD = f"wildlink/{NODE_ID}/cmd"
TOPIC_RES = f"wildlink/{NODE_ID}/res"

current_commands = {}

def on_message(client, userdata, msg):
    global current_commands
    try:
        current_commands.update(json.loads(msg.payload.decode()))
    except: pass

def load_units_from_db():
    loaded = []
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT c.vst_type, c.val_params, cat.vst_class, cat.vst_module
            FROM node_configs c
            JOIN device_catalog cat ON c.vst_type = cat.vst_type
            WHERE c.sys_id = %s AND c.val_enabled = TRUE
        """
        cursor.execute(query, (NODE_ID,))
        for cfg in cursor.fetchall():
            module = importlib.import_module(cfg["vst_module"])
            vst_class = getattr(module, cfg["vst_class"])
            params = json.loads(cfg["val_params"]) if isinstance(cfg["val_params"], str) else cfg["val_params"]
            params["sys_id"] = NODE_ID
            loaded.append(vst_class(params))
            print(f"✅ VST Loaded: {cfg['vst_type']}")
        conn.close()
    except Exception as e:
        print(f"[!!] DB Connection Error: {e}")
    return loaded

def main():
    client = mqtt.Client()
    client.on_message = on_message
    client.connect(MQTT_HOST, 1883, 60)
    client.subscribe(TOPIC_CMD)
    client.loop_start()

    vst_units = load_units_from_db()
    print(f"🚀 WildLink Manager [{NODE_ID}] Operational.")

    try:
        while True:
            all_reports = {}
            for unit in vst_units:
                report = unit.update(current_commands)
                all_reports[unit.val_name] = report
            
            if all_reports:
                client.publish(TOPIC_RES, json.dumps(all_reports))
            
            current_commands.clear()
            time.sleep(1)
    except KeyboardInterrupt:
        client.loop_stop()

if __name__ == "__main__":
    main()