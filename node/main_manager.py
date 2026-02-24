import sys
import os
import json
import time
import threading
import RPi.GPIO as GPIO

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
        self.sync_interval = 30 
        self.current_config_raw = ""
        self.active_timers = {}
        # キャッシュファイルのパス
        self.config_cache_path = os.path.join(current_dir, "last_config.json")

    def setup_mqtt(self):
        host = os.getenv('MQTT_BROKER') or "192.168.1.102"
        self.mqtt = MQTTClient(host, self.node_id)
        if self.mqtt.connect():
            cmd_topic = f"node/cmd/{self.node_id}"
            self.mqtt.client.subscribe(cmd_topic)
            self.mqtt.client.on_message = self.on_mqtt_message
            print(f"📡 MQTT Connected & Subscribed to {cmd_topic}")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            target = payload.get("target")
            action = payload.get("action")
            cmd_id = payload.get("cmd_id")

            if cmd_id:
                self.db.update_command_status(cmd_id, status="acked")

            if target == "manager" and action == "reload":
                print("⚡ [MQTT] Immediate reload command received!")
                self.load_and_init_units()
            elif target in self.units:
                self.units[target].control(payload)
                if cmd_id:
                    self.db.update_command_status(cmd_id, status="completed")
        except Exception as e:
            print(f"❌ [MQTT] Error: {e}")

    def save_config_to_cache(self, configs):
        """ローカルJSONに設定を強制保存する"""
        try:
            with open(self.config_cache_path, 'w') as f:
                json.dump(configs, f, indent=4)
            print(f"💾 [Manager] Config cached to {self.config_cache_path}")
        except Exception as e:
            print(f"❌ [Manager] Cache save error: {e}")

    def load_and_init_units(self):
        """DBから設定を読み込み、中身に変更がある場合のみキャッシュ更新とリロードを行う"""
        configs = self.db.fetch_node_config(self.node_id)
        
        # DB失敗時の処理
        if not configs:
            if not self.units: # まだ何も起動していない時だけキャッシュを試す
                print("⚠️ [Manager] DB fetch failed. Trying local cache...")
                if os.path.exists(self.config_cache_path):
                    with open(self.config_cache_path, 'r') as f:
                        configs = json.load(f)
                    print("📋 [Manager] Local cache loaded (Survival Mode).")
                else:
                    return
            else:
                return # 既に動いているなら、何もしない（今の設定を維持）

        # 取得したデータを文字列化して比較（ソートして順序の差を無視）
        new_config_raw = json.dumps(configs, sort_keys=True, default=str)
        
        # 【重要】前回と全く同じなら、ここで何もしないで終了
        if new_config_raw == self.current_config_raw:
            return 

        # --- ここから下は「変更があった時」だけ実行される ---
        self.current_config_raw = new_config_raw
        
        # キャッシュを更新
        self.save_config_to_cache(configs)
        
        print("🔄 [Manager] Config change detected. Reloading units...")

        # タイマーの全キャンセル
        for t in self.active_timers.values():
            t.cancel()
        self.active_timers.clear()

        # 既存ユニットの停止
        for role, unit in self.units.items():
            if hasattr(unit, 'stop'): unit.stop()
        self.units.clear()
        
        GPIO.cleanup()
        GPIO.setmode(GPIO.BCM)

        for cfg in configs:
            role = cfg['vst_type']
            module_name = cfg['vst_module']
            class_name = cfg['vst_class']
            full_class_name = f"VST_{class_name}"
            params = cfg['val_params']

            try:
                module = __import__(f"node.{module_name}", fromlist=[full_class_name])
                vst_class = getattr(module, full_class_name)
                unit = vst_class(role, params, self.mqtt, self.on_event)
                self.units[role] = unit
                print(f"✅ [{role}] Loaded")
            except Exception as e:
                print(f"❌ [{role}] Load failed: {e}")

    def on_event(self, source_role, event_type):
        source_unit = self.units.get(source_role)
        if not (source_unit and source_unit.params.get("val_enabled", True)): return

        target_role = source_unit.params.get("act_target")
        duration = source_unit.params.get("val_interval", 30)
        
        if target_role in self.units:
            target_unit = self.units[target_role]
            new_status = False

            if event_type == "button_pressed":
                is_active = getattr(target_unit, "gate_open", False)
                new_status = not is_active
                print(f"🔘 [Toggle] {source_role} -> {target_role}: {new_status}")
                target_unit.control({"act_run": new_status})
                
            elif event_type == "motion_detected":
                new_status = True
                print(f"🏃 [Motion] {source_role} -> {target_role}: ON")
                target_unit.control({"act_run": True})

            if target_role in self.active_timers:
                self.active_timers[target_role].cancel()

            if new_status and duration > 0:
                t = threading.Timer(duration, self._safe_close, args=[target_role])
                t.daemon = True
                self.active_timers[target_role] = t
                t.start()

    def _safe_close(self, role):
        if role in self.units:
            self.units[role].control({"act_run": False})

    def run(self):
        self.setup_mqtt()
        self.load_and_init_units()
        print(f"🚀 Node {self.node_id} is running.")
        
        try:
            while True:
                now = time.time()
                if now - self.last_sync_time > self.sync_interval:
                    self.db.update_node_heartbeat(self.node_id, status="online")
                    self.load_and_init_units() 
                    self.last_sync_time = now

                for unit in self.units.values():
                    if hasattr(unit, 'poll'): unit.poll()
                time.sleep(0.1)
        except KeyboardInterrupt:
            GPIO.cleanup()

if __name__ == "__main__":
    manager = MainManager("node_001")
    manager.run()