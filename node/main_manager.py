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

class MainManager:
    def __init__(self, node_id):
        self.node_id = node_id
        self.db = DBBridge()
        self.units = {}
        self.mqtt = None
        self.last_sync_time = 0
        self.sync_interval = 30  # DB同期とレポートの周期
        self.current_config_raw = ""
        self.active_timers = {}
        self.config_cache_path = os.path.join(current_dir, "last_config.json")

    def setup_mqtt(self):
        host = os.getenv('MQTT_BROKER') or "192.168.1.102"
        self.mqtt = MQTTClient(host, self.node_id)
        if self.mqtt.connect():
            # 全コマンド購読 (vst/node_001/cmd/+)
            cmd_topic = f"vst/{self.node_id}/cmd/+" 
            self.mqtt.client.subscribe(cmd_topic)
            self.mqtt.client.on_message = self.on_mqtt_message
            print(f"📡 MQTT Connected & Subscribed to {cmd_topic}")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            target = payload.get("target")
            cmd_id = payload.get("cmd_id")
            res_topic = f"vst/{self.node_id}/res"

            if cmd_id:
                # 1. Ack (受領報告)
                self.mqtt.client.publish(res_topic, json.dumps({"cmd_id": cmd_id, "val_status": "acked"}))

            if target in self.units:
                # 2. 実行
                try:
                    self.units[target].control(payload)
                    if cmd_id:
                        self.mqtt.client.publish(res_topic, json.dumps({
                            "cmd_id": cmd_id, "val_status": "success", "log_code": 200
                        }))
                except Exception as unit_e:
                    if cmd_id:
                        self.mqtt.client.publish(res_topic, json.dumps({
                            "cmd_id": cmd_id, "val_status": "error", "log_code": 500, "log_msg": str(unit_e)
                        }))
            
            # マネージャー自身へのコマンド（リロードなど）
            if target == "manager" and payload.get("action") == "reload":
                print("⚡ [MQTT] Reload command received")
                self.load_and_init_units()

        except Exception as e:
            print(f"❌ [MQTT] Error: {e}")

    def send_report(self):
        """現在の全ユニットの状態をHubへMQTT送信"""
        if not self.mqtt: return
        
        report = {
            "sys_monitor": {
                "sys_cpu_t": self._get_cpu_temp(),
                "net_rssi": -50, 
                "log_msg": "System healthy"
            },
            "units": {}
        }
        for role, unit in self.units.items():
            # ユニットからステータス辞書を取得
            report["units"][role] = getattr(unit, "status_dict", {"val_status": "unknown"})
        
        topic = f"vst/{self.node_id}/report"
        self.mqtt.publish(topic, report)
        print(f"📊 [Manager] Report sent to {topic}")

    def _get_cpu_temp(self):
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                return float(f.read()) / 1000.0
        except: return 0.0

    def load_and_init_units(self):
        """DBから最新設定を読み込み、変更があれば反映"""
        configs = self.db.fetch_node_config(self.node_id)
        if not configs:
            if not self.units and os.path.exists(self.config_cache_path):
                with open(self.config_cache_path, 'r') as f: configs = json.load(f)
            else: return

        new_config_raw = json.dumps(configs, sort_keys=True, default=str)
        if new_config_raw == self.current_config_raw: return 

        self.current_config_raw = new_config_raw
        with open(self.config_cache_path, 'w') as f: json.dump(configs, f)
        
        print("🔄 [Manager] Config change detected. Reloading...")
        for t in self.active_timers.values(): t.cancel()
        self.active_timers.clear()
        
        for unit in self.units.values():
            if hasattr(unit, 'stop'): unit.stop()
        self.units.clear()
        
        GPIO.cleanup()
        GPIO.setmode(GPIO.BCM)

        for cfg in configs:
            role, mod, cls, params = cfg['vst_type'], cfg['vst_module'], cfg['vst_class'], cfg['val_params']
            try:
                module = __import__(f"node.{mod}", fromlist=[f"VST_{cls}"])
                vst_class = getattr(module, f"VST_{cls}")
                self.units[role] = vst_class(role, params, self.mqtt, self.on_event)
                print(f"✅ [{role}] Loaded")
            except Exception as e: print(f"❌ [{role}] Load failed: {e}")

    def on_event(self, source_role, event_type):
        """ユニット間連携 (Button -> Camera など)"""
        source_unit = self.units.get(source_role)
        if not source_unit: return
        target_role = source_unit.params.get("act_target")
        duration = source_unit.params.get("val_interval", 30)
        
        if target_role in self.units:
            target_unit = self.units[target_role]
            new_run = False
            if event_type == "button_pressed":
                new_run = not getattr(target_unit, "act_run", False)
            elif event_type == "motion_detected":
                new_run = True
            
            target_unit.control({"act_run": new_run})
            if target_role in self.active_timers: self.active_timers[target_role].cancel()
            if new_run and duration > 0:
                t = threading.Timer(duration, lambda: target_unit.control({"act_run": False}))
                t.daemon = True
                self.active_timers[target_role] = t
                t.start()

    def run(self):
        self.setup_mqtt()
        self.load_and_init_units()
        print(f"🚀 Node {self.node_id} is running.")
        try:
            while True:
                now = time.time()
                # 30秒おきに同期とレポート
                if now - self.last_sync_time > self.sync_interval:
                    self.db.update_node_heartbeat(self.node_id, status="online")
                    self.load_and_init_units() 
                    self.send_report()
                    self.last_sync_time = now

                for unit in self.units.values():
                    if hasattr(unit, 'poll'): unit.poll()
                time.sleep(0.1)
        except KeyboardInterrupt: 
            print("\n👋 Manager shutting down...")
            GPIO.cleanup()

if __name__ == "__main__":
    manager = MainManager("node_001")
    manager.run()