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
            
        topic_sys_id = topic_parts[1]
        msg_type = topic_parts[2]
        
        payload = json.loads(msg.payload.decode())
        sys_id = payload.get("sys_id") or topic_sys_id

        # --- A. ノードからのレスポンス (res) 処理 ---
        if msg_type == "res":
            # WES 2026 準拠: ref_cmd_id または cmd_id を取得
            cmd_id = payload.get("ref_cmd_id") or payload.get("cmd_id")
            cmd_status = payload.get("cmd_status") or payload.get("val_status") # フォールバック
            
            if not cmd_id: return

            # 1. 受領通知 (acknowledged) の場合
            if cmd_status == "acknowledged":
                sql_ack = "UPDATE node_commands SET acked_at = NOW(3) WHERE id = %s AND acked_at IS NULL"
                db._execute(sql_ack, (cmd_id,))
                logger.info(f"🕒 [ACK] Command {cmd_id} acknowledged by {sys_id}")

            # 2. 完了 (completed) または 失敗 (failed/error) の場合
            elif cmd_status in ["completed", "failed", "error", "success"]:
                # 完了時刻と最終ステータスを書き込む
                sql_final = """
                    UPDATE node_commands 
                    SET val_status = %s, log_code = %s, log_msg = %s, 
                        val_res_payload = %s, completed_at = NOW(3) 
                    WHERE id = %s
                """
                # val_status には物理状態 (streaming等) を入れる
                final_val_status = payload.get("val_status") or ("error" if cmd_status == "failed" else "idle")
                
                db._execute(sql_final, (
                    final_val_status, 
                    payload.get("log_code", 200), 
                    payload.get("log_msg", ""), 
                    json.dumps(payload), 
                    cmd_id
                ))

                # 現在のステータス(node_status_current)も同期
                role_name = payload.get("role") or payload.get("vst_role_name")
                if role_name:
                    db.update_vst_status(sys_id, role_name, final_val_status)
                    logger.info(f"✅ [Final] Command {cmd_id} {cmd_status}. Status: {role_name}->{final_val_status}")

        # --- B. ノードからのレポート (report) 処理 ---
        elif msg_type == "report":
            sys_mon = payload.get("sys_monitor", {})
            units_data = payload.get("units", {})
            
            # 1. system_logs への保存 (DBBridge経由に統合)
            log_msg = sys_mon.get("log_msg", "System Report")
            ext_info = json.dumps({
                "cpu_t": sys_mon.get("sys_cpu_t"),
                "board_t": sys_mon.get("sys_board_t"),
                "rssi": sys_mon.get("net_rssi")
            })
            db.insert_system_log(sys_id, "report", "info", log_msg, code=200, ext=ext_info)

            # 2. node_data への保存（環境センサー値など：ハイブリッド型）
            # env_ で始まるキーを環境データとして抽出
            env_data = {
                'temp': sys_mon.get("env_temp"),
                'hum':  sys_mon.get("env_hum"),
                'pres': sys_mon.get("env_pres"),
                'lux':  sys_mon.get("env_lux")
            }
            
            # role_name は、一括レポートの場合は "node_system" などで固定
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
    # ワイルドカードを使用して全ノードを監視
    mqtt.client.subscribe("vst/+/report")
    mqtt.client.subscribe("vst/+/res")
    logger.info("🚀 WildLink 2026 Status Engine (Role-aware) started...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        mqtt.disconnect()