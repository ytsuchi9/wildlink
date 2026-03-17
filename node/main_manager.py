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
        # node_id から sys_id へ名称統一
        self.sys_id = sys_id
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
        # 接続用クライアントIDも sys_id を使用
        self.mqtt = MQTTClient(host, self.sys_id)
        if self.mqtt.connect():
            # 購読トピックを 2026年規格の sys_id パスへ
            cmd_topic = f"vst/{self.sys_id}/cmd/+" 
            self.mqtt.client.subscribe(cmd_topic)
            self.mqtt.client.on_message = self.on_mqtt_message
            logger.info(f"📡 MQTT Connected & Subscribed to {cmd_topic}")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            target = payload.get("target")
            cmd_id = payload.get("cmd_id")
            # 応答トピックも sys_id に統一
            res_topic = f"vst/{self.sys_id}/res"

            if cmd_id:
                # ACK (受け取った旨) を即座に返信
                self.mqtt.client.publish(res_topic, json.dumps({
                    "sys_id": self.sys_id,
                    "cmd_id": cmd_id, 
                    "val_status": "acked"
                }))

            if target in self.units:
                try:
                    self.units[target].execute_logic(payload)
                    if cmd_id:
                        # 成功報告
                        self.mqtt.client.publish(res_topic, json.dumps({
                            "sys_id": self.sys_id,
                            "cmd_id": cmd_id, 
                            "val_status": "success", 
                            "log_code": 200,
                            "target_status": getattr(self.units[target], 'val_status', 'unknown')
                        }))
                except Exception as unit_e:
                    logger.error(f"❌ [{target}] Execution failed: {unit_e}")
                    if cmd_id:
                        self.mqtt.client.publish(res_topic, json.dumps({
                            "sys_id": self.sys_id,
                            "cmd_id": cmd_id, 
                            "val_status": "error", 
                            "log_code": 500, 
                            "log_msg": str(unit_e)
                        }))
            elif target == "manager" and payload.get("action") == "reload":
                logger.info("🔄 Reload command received via MQTT")
                self.load_and_init_units()

        except Exception as e:
            logger.error(f"❌ [MQTT] Error: {e}")

    def load_and_init_units(self):
        """DBから最新設定を読み込み、キャッシュと比較して変更があれば反映"""
        # 引数を sys_id に修正
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
                logger.error("❌ [Manager] No config available (DB fail & No cache)")
                return

        current_data_set = {"configs": new_configs, "links": new_links}
        new_config_raw = json.dumps(current_data_set, sort_keys=True, default=str)
        
        if new_config_raw == self.current_config_raw:
            return

        logger.info("🔄 [Manager] Config/Links change detected. Synchronizing...")
        
        self.current_config_raw = new_config_raw
        self.links = new_links
        with open(self.config_cache_path, 'w') as f:
            json.dump(current_data_set, f)
        
        # 既存ユニットとタイマーのクリーンアップ
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
            role = cfg['vst_type']
            cls_name = cfg['vst_class']
            mod_name = cfg.get('vst_module', f"vst_{cls_name.lower()}")
            params = cfg.get('val_params', {})
            
            unit_config = {
                "hw_driver": cfg.get("hw_driver"),
                "hw_bus_addr": cfg.get("hw_bus_addr"),
                "vst_role_name": cfg.get("vst_role_name")
            }

            try:
                module = __import__(f"node.{mod_name}", fromlist=[f"VST_{cls_name}"])
                vst_class = getattr(module, f"VST_{cls_name}")
                
                import inspect
                sig = inspect.signature(vst_class.__init__)
                # ユニット側にも sys_id を渡す（必要なら）
                if 'config' in sig.parameters:
                    self.units[role] = vst_class(role, params, self.mqtt, self.on_event, config=unit_config)
                else:
                    self.units[role] = vst_class(role, params, self.mqtt, self.on_event)
                
                logger.info(f"✅ [{role}] Activated ({unit_config['hw_driver']} @ {unit_config['hw_bus_addr']})")
            except Exception as e: 
                logger.error(f"❌ [{role}] Activation failed: {e}")

    def on_event(self, source_role, event_type):
        logger.debug(f"🔔 [Event] Source: {source_role} Type: {event_type}")
        
        matched_links = [l for l in self.links if l['source_role'] == source_role]
        
        if not matched_links:
            return

        for link in matched_links:
            target_role = link['target_role']
            duration = link['val_interval']
            
            if target_role in self.units:
                target_unit = self.units[target_role]
                is_active = getattr(target_unit, "act_run", False)
                new_run = not is_active if duration == 0 else True
                
                logger.info(f"➡️ [Route] {source_role} -> {target_role} (Action: {'TOGGLE' if duration == 0 else 'ON'})")
                target_unit.execute_logic({"act_run": new_run})
                
                if target_role in self.active_timers:
                    self.active_timers[target_role].cancel()
                
                if new_run and duration > 0:
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
                    # ハートビート更新
                    self.db.update_node_heartbeat(self.sys_id, status="online")
                    self.load_and_init_units() 
                    self.last_sync_time = now
                
                for unit in self.units.values():
                    if hasattr(unit, 'poll'): 
                        unit.poll()
                
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("👋 Stopping Manager...")
            self.mqtt.client.loop_stop()
            GPIO.cleanup()

if __name__ == "__main__":
    # 環境変数から sys_id を取得。なければデフォルト node_001
    sys_id = os.getenv("SYS_ID", "node_001")
    manager = MainManager(sys_id)
    manager.run()