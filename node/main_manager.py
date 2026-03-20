import sys
import os
import json
import time
import threading
import RPi.GPIO as GPIO

# パス解決
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from common.db_bridge import DBBridge
from common.mqtt_client import MQTTClient
from common.logger_config import get_logger

# ロガー初期化
logger = get_logger("main_manager")

class MainManager:
    def __init__(self, sys_id):
        self.sys_id = sys_id
        # ロガーをノード名入りで再取得
        self.logger = get_logger(f"{sys_id}:main_manager")
        self.db = DBBridge()
        self.units = {}
        self.links = []
        self.active_timers = {}
        self.current_config_raw = ""
        self.last_sync_time = 0
        self.sync_interval = 30
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_cache_path = os.path.join(base_dir, 'last_config.json')

    def setup_mqtt(self):
        host = os.getenv('MQTT_BROKER') or "192.168.1.102"
        self.mqtt = MQTTClient(host, self.sys_id)
        if self.mqtt.connect():
            # 2026年規格: vst/{sys_id}/cmd/+
            cmd_topic = f"vst/{self.sys_id}/cmd/+" 
            self.mqtt.client.subscribe(cmd_topic)
            self.mqtt.client.on_message = self.on_mqtt_message
            logger.info(f"📡 MQTT Connected & Subscribed to {cmd_topic}")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            # 2026年仕様: roleを優先、なければtargetを見る
            target_role = payload.get("role") or payload.get("target")
            cmd_id = payload.get("cmd_id")
            res_topic = f"vst/{self.sys_id}/res"

            if cmd_id:
                # ACK (即座に受信報告)
                self.mqtt.client.publish(res_topic, json.dumps({
                    "sys_id": self.sys_id,
                    "cmd_id": cmd_id, 
                    "val_status": "acked"
                }))

            # 役割名(target_role)でユニットを検索
            if target_role in self.units:
                try:
                    # 💡 実行！ここでの成否を判定
                    success = self.units[target_role].execute_logic(payload)
                    if cmd_id:
                        status_str = "success" if success else "error"
                        self.mqtt.client.publish(res_topic, json.dumps({
                            "sys_id": self.sys_id,
                            "cmd_id": cmd_id, 
                            "role": target_role, # 💡 roleを付加
                            "val_status": status_str, 
                            "log_code": 200 if success else 500,
                            "target_status": getattr(self.units[target_role], 'val_status', 'unknown')
                        }))
                except Exception as unit_e:
                    self.logger.error(f"❌ [{target_role}] Execution failed: {unit_e}")
                    if cmd_id:
                        self.mqtt.client.publish(res_topic, json.dumps({
                            "sys_id": self.sys_id,
                            "cmd_id": cmd_id, 
                            "role": target_role, # 💡 エラー時もroleを付加
                            "val_status": "error", 
                            "log_code": 500, 
                            "log_msg": str(unit_e)
                        }))
            elif target_role == "manager" and payload.get("action") == "reload":
                logger.info("🔄 Reload command received via MQTT")
                self.load_and_init_units()

        except Exception as e:
            logger.error(f"❌ [MQTT] Error: {e}")

    def load_and_init_units(self):
        """DBから有効(is_active=1)な設定を読み込み、反映"""
        new_configs = self.db.fetch_node_config(self.sys_id)
        new_links = self.db.fetch_vst_links(self.sys_id)
        
        if new_configs is None:
            if os.path.exists(self.config_cache_path):
                logger.warning("⚠️ [Manager] DB connection failed. Loading from cache...")
                with open(self.config_cache_path, 'r') as f:
                    cached_data = json.load(f)
                    new_configs = cached_data.get("configs", [])
                    new_links = cached_data.get("links", [])
            else:
                logger.error("❌ [Manager] No config available")
                return

        current_data_set = {"configs": new_configs, "links": new_links}
        new_config_raw = json.dumps(current_data_set, sort_keys=True, default=str)
        
        if new_config_raw == self.current_config_raw:
            return

        logger.info("🔄 [Manager] Config/Links change detected. Re-initializing units...")
        
        self.current_config_raw = new_config_raw
        self.links = new_links
        with open(self.config_cache_path, 'w') as f:
            json.dump(current_data_set, f)
        
        # 既存リソースの解放
        for t in self.active_timers.values(): 
            t.cancel()
        self.active_timers.clear()
        
        for unit in self.units.values():
            if hasattr(unit, 'stop'): 
                unit.stop()
        self.units.clear()
        
        GPIO.cleanup()
        GPIO.setmode(GPIO.BCM)

        # ユニットの初期化
        for cfg in new_configs:
            vst_type = cfg['vst_type']
            role_name = cfg.get('vst_role_name') or vst_type # 役割名をキーにする
            cls_name = cfg['vst_class']
            mod_name = cfg.get('vst_module', f"vst_{cls_name.lower()}")
            params = cfg.get('val_params', {})
            
            unit_config = {
                "hw_driver": cfg.get("hw_driver"),
                "hw_bus_addr": cfg.get("hw_bus_addr"),
                "vst_role_name": role_name
            }

            try:
                module = __import__(f"node.{mod_name}", fromlist=[f"VST_{cls_name}"])
                vst_class = getattr(module, f"VST_{cls_name}")
                
                # 2026年仕様: vst_role_name を識別子として渡す
                self.units[role_name] = vst_class(role_name, params, self.mqtt, self.on_event, config=unit_config)
                
                logger.info(f"✅ [{role_name}] Activated as {vst_type}")
            except Exception as e: 
                logger.error(f"❌ [{role_name}] Activation failed: {e}")

    def on_event(self, source_role, event_type):
        """連動設定(Links)の実行ロジック"""
        logger.debug(f"🔔 [Event] Source: {source_role} Type: {event_type}")
        
        matched_links = [l for l in self.links if l['source_role'] == source_role and l.get('event_type') == event_type]
        
        for link in matched_links:
            target_role = link['target_role']
            duration = link.get('val_interval', 0)
            
            if target_role in self.units:
                target_unit = self.units[target_role]
                # act_run を制御
                is_running = getattr(target_unit, "act_run", False)
                new_state = not is_running if duration == 0 else True
                
                logger.info(f"➡️ [Route] {source_role} -> {target_role} (State: {new_state})")
                target_unit.execute_logic({"act_run": new_state})
                
                # タイマー制御
                if target_role in self.active_timers:
                    self.active_timers[target_role].cancel()
                
                if new_state and duration > 0:
                    t = threading.Timer(duration, lambda r=target_role: self.units[r].execute_logic({"act_run": False}))
                    t.daemon = True
                    self.active_timers[target_role] = t
                    t.start()

    def run(self):
        self.setup_mqtt()
        self.mqtt.client.loop_start() 
        self.load_and_init_units()
        
        logger.info(f"📡 Main Manager [{self.sys_id}] is running...")
        try:
            while True:
                now = time.time()
                if now - self.last_sync_time > self.sync_interval:
                    # ハートビート更新と構成の再チェック
                    self.db.update_node_heartbeat(self.sys_id, status="online")
                    self.load_and_init_units() 
                    self.last_sync_time = now
                
                # 各ユニットの定期処理（センサー読み取り等）
                for unit in list(self.units.values()):
                    if hasattr(unit, 'poll'): 
                        unit.poll()
                
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("👋 Stopping Manager...")
            self.mqtt.client.loop_stop()
            GPIO.cleanup()

if __name__ == "__main__":
    sys_id = os.getenv("SYS_ID", "node_001")
    manager = MainManager(sys_id)
    manager.run()