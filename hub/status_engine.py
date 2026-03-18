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
        # トピック構成: vst/{sys_id}/{msg_type}
        topic_parts = msg.topic.split('/')
        if len(topic_parts) < 3:
            return
            
        # トピックから情報を抽出
        topic_sys_id = topic_parts[1]
        msg_type = topic_parts[2]
        
        payload = {}
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            logger.error(f"⚠️ Invalid JSON received on {msg.topic}")
            return
        
        # ペイロード内に sys_id があれば優先、なければトピックから採用
        sys_id = payload.get("sys_id") or topic_sys_id

        # --- A. ノードからのレスポンス (res) 処理 ---
        if msg_type == "res":
            cmd_id = payload.get("cmd_id")
            val_status = payload.get("val_status")
            if not cmd_id:
                return
            
            # 1. コマンド履歴(node_commands)を更新
            # ※ node_commands は履歴なので直接UPDATEでOK（設計維持）
            sql_cmd = """
                UPDATE node_commands 
                SET val_status = %s, log_code = %s, log_msg = %s, val_res_payload = %s, completed_at = NOW(3) 
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
                # コマンド内容を再確認してステータス反映
                row = db.fetch_one("SELECT cmd_json FROM node_commands WHERE id = %s", (cmd_id,))
                if row:
                    cmd_info = json.loads(row[0])
                    # 2026年版：vst_type ではなく role (役割名) を優先的に探す
                    role_name = cmd_info.get("role") or cmd_info.get("target") or cmd_info.get("vst_type")
                    action = cmd_info.get("action")
                    
                    if role_name:
                        # start命令なら streaming、それ以外（stop等）なら idle
                        new_status = 'streaming' if action == 'start' else 'idle'
                        # DBBridgeの新しい role 対応メソッドを使用
                        db.update_vst_status(sys_id, role_name, new_status)
                        logger.info(f"[{sys_id}] ⚡ Status synced: {role_name} -> {new_status}")

            logger.debug(f"[{sys_id}] ✅ Command {cmd_id} updated to {val_status}")

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