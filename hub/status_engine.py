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
        if len(topic_parts) < 3:
            return
            
        node_id = topic_parts[1]
        msg_type = topic_parts[2]
        payload = json.loads(msg.payload.decode())
        
        sys_id = payload.get("sys_id") or node_id

        # --- A. ノードからのレスポンス (res) 処理 ---
        if msg_type == "res":
            cmd_id = payload.get("cmd_id")
            val_status = payload.get("val_status")
            if not cmd_id:
                return
            
            # 1. コマンド履歴(node_commands)を更新
            sql_cmd = """
                UPDATE node_commands 
                SET val_status = %s, log_code = %s, log_msg = %s, res_payload = %s, completed_at = NOW(3) 
                WHERE id = %s
            """
            db._execute(sql_cmd, (
                val_status, 
                payload.get("log_code"), 
                payload.get("log_msg"), 
                json.dumps(payload), 
                cmd_id
            ))

            # 2. 実行成功時のみ、現在のステータスを同期
            if val_status == "success":
                row = db.fetch_one("SELECT cmd_json FROM node_commands WHERE id = %s", (cmd_id,))
                if row:
                    cmd_info = json.loads(row[0])
                    vst_type = cmd_info.get("target") or cmd_info.get("vst_type")
                    action = cmd_info.get("action")
                    
                    if vst_type:
                        new_status = 'streaming' if action == 'start' else 'idle'
                        db.update_vst_status(sys_id, vst_type, new_status)
                        logger.info(f"[{sys_id}] ⚡ Status synced: {vst_type} -> {new_status}")

            logger.debug(f"[{sys_id}] ✅ Command {cmd_id} updated to {val_status}")

        # --- B. ノードからのレポート (report) 処理 ---
        elif msg_type == "report":
            sys_mon = payload.get("sys_monitor", {})
            
            # system_logs への保存（直接SQLを実行）
            sql_log = """
                INSERT INTO system_logs (sys_id, log_level, sys_cpu_t, sys_board_t, net_rssi, log_msg) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            db._execute(sql_log, (
                sys_id, "info", 
                sys_mon.get("sys_cpu_t"), sys_mon.get("sys_board_t"), 
                sys_mon.get("net_rssi"), sys_mon.get("log_msg")
            ))

            # node_data への保存（環境センサー値など）
            units_data = payload.get("units", {})
            env_data = {k: v for k, v in sys_mon.items() if k.startswith("env_")}
            
            sql_data = """
                INSERT INTO node_data (sys_id, env_temp, env_hum, env_pres, env_lux, raw_data) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            db._execute(sql_data, (
                sys_id, 
                env_data.get("env_temp"), env_data.get("env_hum"), 
                env_data.get("env_pres"), env_data.get("env_lux"), 
                json.dumps(units_data)
            ))
            
            # 生存報告(nodesテーブル)を更新
            db.update_node_heartbeat(sys_id, "online")
            logger.debug(f"[{sys_id}] 📥 Metrics archived.")

    except Exception as e:
        logger.error(f"❌ Status Engine Error: {e}")

mqtt = MQTTClient(BROKER, "hub_status_engine")
mqtt.client.on_message = on_message
if mqtt.connect():
    mqtt.client.subscribe("vst/+/report")
    mqtt.client.subscribe("vst/+/res")
    logger.info("🚀 WildLink 2026 Status Engine (Config-Sync Mode) started...")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        mqtt.disconnect()