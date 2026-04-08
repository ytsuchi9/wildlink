import sys
import os
import time
import json

# --- パス解決 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
wildlink_root = os.path.dirname(current_dir)
sys.path.append(os.path.join(wildlink_root, "common"))

from mqtt_client import MQTTClient
from db_bridge import DBBridge
from logger_config import get_logger

# ロガー初期化
logger = get_logger("status_engine")

BROKER = os.getenv("MQTT_BROKER", "localhost")

class WildLinkStatusEngine:
    """
    WildLink Event Standard (WES) 2026 準拠
    役割: ノードから定期的に飛んでくるテレメトリ(report)を解析し、
    環境データ(node_data)と生存信号(heartbeat)を更新する。
    """
    def __init__(self):
        self.db = DBBridge()

    def on_message(self, client, userdata, msg):
        try:
            topic_parts = msg.topic.split('/')
            if len(topic_parts) < 3: return
                
            # トピック解析: nodes/{sys_id}/{vst_role}/report
            if topic_parts[0] == "nodes":
                sys_id = topic_parts[1]
                vst_role = topic_parts[2]
                msg_type = topic_parts[3] if len(topic_parts) > 3 else None
            else:
                # 旧トピック(vst/...)対応
                sys_id = topic_parts[1]
                vst_role = "system" 
                msg_type = topic_parts[2]

            if msg_type != "report":
                return # res/event/cmd は hub_manager 等が処理するためスルー

            payload = json.loads(msg.payload.decode())
            
            # 1. 生存報告 (nodesテーブルの last_seen / status を更新)
            # これにより UI 上で「オンライン」判定が行われます
            self.db.update_node_heartbeat(sys_id, status="online")

            # 2. システムメトリクスの抽出 (sys_ プレフィックス)
            sys_mon = payload.get("sys_monitor", {})
            if sys_mon:
                log_msg = f"Report from {vst_role}"
                ext_info = {
                    "cpu_t": sys_mon.get("sys_cpu_t"),
                    "board_t": sys_mon.get("sys_board_t"),
                    "rssi": sys_mon.get("net_rssi"),
                    "volt": sys_mon.get("sys_volt")
                }
                # システムログに低頻度メトリクスを記録
                self.db.insert_system_log(
                    sys_id, 
                    vst_role, 
                    "info", 
                    log_msg, 
                    code=200, 
                    ext=json.dumps(ext_info)
                )

            # 3. 環境データ・センサー値の保存 (node_data)
            # WES 2026: env_ プレフィックスを持つものを抽出
            env_data = {k: v for k, v in payload.items() if k.startswith("env_")}
            
            # units_data (各VSTの内部状態) が含まれている場合は raw_json として保存
            units_data = payload.get("units", {})

            if env_data or units_data:
                # node_data テーブルへ時系列データとして挿入
                self.db.insert_node_data(
                    sys_id, 
                    vst_role, 
                    env_data, 
                    raw_json=json.dumps(units_data)
                )
            
            logger.debug(f"📥 [report] {sys_id}:{vst_role} Metrics archived.")

        except Exception as e:
            logger.error(f"❌ Status Engine Message Error: {e}")

    def run(self):
        mqtt = MQTTClient(BROKER, "wildlink_status_engine")
        mqtt.client.on_message = self.on_message
        
        if mqtt.connect():
            # レポート系トピックのみを購読
            mqtt.client.subscribe("vst/+/report")
            mqtt.client.subscribe("nodes/+/+/report")
            
            logger.info("🚀 WildLink 2026 Status Engine (Telemetry Specialist) started.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                mqtt.disconnect()

if __name__ == "__main__":
    WildLinkStatusEngine().run()