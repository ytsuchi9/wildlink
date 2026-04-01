import sys
import os
import time
import json

# パス解決
current_dir = os.path.dirname(os.path.abspath(__file__))
wildlink_root = os.path.dirname(current_dir)
sys.path.append(os.path.join(wildlink_root, "common"))

from mqtt_client import MQTTClient
from db_bridge import DBBridge
from logger_config import get_logger

# ロガー初期化 (log_type="status_engine")
logger = get_logger("status_engine")

BROKER = os.getenv("MQTT_BROKER", "localhost")

def on_message(client, userdata, msg):
    db = DBBridge() 
    
    try:
        topic_parts = msg.topic.split('/')
        if len(topic_parts) < 3: return
            
        # WES 2026 の nodes/sys_id/role/report と、旧 vst/sys_id/report の両対応
        if topic_parts[0] == "nodes":
            sys_id = topic_parts[1]
            role = topic_parts[2]
            msg_type = topic_parts[3] if len(topic_parts) > 3 else None
        else:
            sys_id = topic_parts[1]
            msg_type = topic_parts[2]

        if msg_type != "report":
            return # report 以外は無視（hub_managerに任せる）

        payload = json.loads(msg.payload.decode())
        sys_id = payload.get("sys_id") or sys_id

        # --- ノードからの定期レポート (report) 処理 ---
        sys_mon = payload.get("sys_monitor", {})
        units_data = payload.get("units", {})
        
        # 1. system_logs への保存
        log_msg = sys_mon.get("log_msg", "System Report")
        ext_info = json.dumps({
            "cpu_t": sys_mon.get("sys_cpu_t"),
            "board_t": sys_mon.get("sys_board_t"),
            "rssi": sys_mon.get("net_rssi")
        })
        db.insert_system_log(sys_id, "report", "info", log_msg, code=200, ext=ext_info)

        # 2. node_data への保存（環境センサー値など）
        env_data = {
            'temp': sys_mon.get("env_temp"),
            'hum':  sys_mon.get("env_hum"),
            'pres': sys_mon.get("env_pres"),
            'lux':  sys_mon.get("env_lux")
        }
        
        # role_name は一括レポートの場合は "node_system" などで固定
        db.insert_node_data(sys_id, "node_system", env_data, raw_json=json.dumps(units_data))
        
        # 3. 生存報告(nodesテーブル)を更新
        db.update_node_heartbeat(sys_id, status="online")
        logger.debug(f"[{sys_id}] 📥 Metrics and Heartbeat archived.")

    except Exception as e:
        logger.error(f"❌ Status Engine Error: {e}")

# MQTTクライアント起動
mqtt = MQTTClient(BROKER, "hub_status_engine")
mqtt.client.on_message = on_message
if mqtt.connect():
    # レポートのみを購読 (新旧両方のトピック構造をカバー)
    mqtt.client.subscribe("vst/+/report")
    mqtt.client.subscribe("nodes/+/+/report")
    logger.info("🚀 WildLink 2026 Status Engine (Metrics Only) started...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        mqtt.disconnect()