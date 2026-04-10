import sys
import os
import time
import json

# --- パス解決 (WES 2026 標準スタイル) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
wildlink_root = os.path.abspath(os.path.join(current_dir, ".."))

if wildlink_root not in sys.path:
    sys.path.insert(0, wildlink_root)

# --- WildLink 共通モジュールのインポート ---
try:
    from common.mqtt_client import MQTTClient
    from common.db_bridge import DBBridge
    from common.logger_config import get_logger
    from common import config_loader
except ImportError as e:
    print(f"FATAL: Module import failed: {e}")
    sys.exit(1)

# ロガー初期化
logger = get_logger("status_engine")

# 設定の取得
BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PREFIX = getattr(config_loader, 'MQTT_PREFIX', 'wildlink')
GROUP_ID    = getattr(config_loader, 'GROUP_ID', 'home_internal')

class WildLinkStatusEngine:
    def __init__(self):
        try:
            self.db = DBBridge()
        except Exception as e:
            logger.error(f"❌ Failed to connect to DB: {e}")
            sys.exit(1)

    def on_message(self, client, userdata, msg):
        try:
            topic_parts = msg.topic.split('/')
            if len(topic_parts) < 3: return
                
            # 🌟 修正: ハードコードを MQTT_PREFIX に変更
            if topic_parts[0] == MQTT_PREFIX:
                sys_id = topic_parts[2]
                vst_role = topic_parts[3]
                msg_type = topic_parts[4] if len(topic_parts) > 3 else None
            elif topic_parts[0] == "vst":
                # 旧トピック(vst/...)対応
                sys_id = topic_parts[1]
                vst_role = "system" 
                msg_type = topic_parts[2]
            else:
                return # 未知のトピックプレフィックスは無視

            if msg_type != "report":
                return

            payload = json.loads(msg.payload.decode())
            
            # 生存報告
            self.db.update_node_heartbeat(sys_id, status="online")

            # システムメトリクス (sys_)
            sys_mon = payload.get("sys_monitor", {})
            if sys_mon:
                ext_info = {
                    "cpu_t": sys_mon.get("sys_cpu_t"),
                    "rssi": sys_mon.get("net_rssi"),
                    "volt": sys_mon.get("sys_volt")
                }
                self.db.insert_system_log(sys_id, vst_role, "info", "Telemetry received", code=200, ext=json.dumps(ext_info))

            # 環境データ (env_)
            env_data = {k: v for k, v in payload.items() if k.startswith("env_")}
            units_data = payload.get("units", {})

            if env_data or units_data:
                self.db.insert_node_data(sys_id, vst_role, env_data, raw_json=json.dumps(units_data))
            
            logger.debug(f"📥 [report] {sys_id}:{vst_role} Metrics archived.")

        except Exception as e:
            logger.error(f"❌ Message processing error: {e}")

    def run(self):
        logger.info(f"Connecting to MQTT Broker: {BROKER}...")
        mqtt = MQTTClient(BROKER, "wildlink_status_engine")
        mqtt.client.on_message = self.on_message
        
        if mqtt.connect():
            # 🌟 修正: f-string でプレフィックスを動的に設定
            mqtt.client.subscribe("vst/+/report")
            mqtt.client.subscribe(f"{MQTT_PREFIX}/{GROUP_ID}/+/+/report")
            
            logger.info(f"🚀 WildLink 2026 Status Engine started. (Prefix: {MQTT_PREFIX})")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                mqtt.disconnect()
        else:
            # 🌟 修正: 接続失敗時にログを出して終了（これでHub側で原因が追えます）
            logger.error(f"❌ Failed to connect to MQTT Broker at {BROKER}")
            sys.exit(1)

if __name__ == "__main__":
    WildLinkStatusEngine().run()