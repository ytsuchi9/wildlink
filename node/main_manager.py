import os
import sys
import paho.mqtt.client as mqtt
import json
import time
import importlib
from datetime import datetime
from dotenv import load_dotenv

# --- 1. パス解決：node と common の両方を Python に教える ---
current_dir = os.path.dirname(os.path.abspath(__file__)) # /opt/wildlink/node
wildlink_root = os.path.dirname(current_dir)             # /opt/wildlink
common_dir = os.path.join(wildlink_root, "common")

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if common_dir not in sys.path:
    sys.path.insert(0, common_dir)

# --- 2. .env の読み込み ---
# /opt/wildlink/.env を探しに行く
load_dotenv(os.path.join(wildlink_root, ".env"))

SYS_ID = os.getenv("SYS_ID", "node_default")
BROKER_ADDR = os.getenv("MQTT_BROKER", "127.0.0.1")

# --- 3. 自作ベースクラスのインポート ---
from vst_base import WildLinkVSTBase

class WildLinkMainManager:
    def __init__(self):
        self.vsts = {}
        # Callback API v1 の警告が出る場合は最新(v2)への移行も検討できますが、一旦維持
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=SYS_ID)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def load_vsts_from_config(self, config_list):
        for cfg in config_list:
            vst_type = cfg['vst_type']
            module_name = cfg['vst_module']
            class_name = cfg['vst_class']
            params = json.loads(cfg['val_params']) if isinstance(cfg['val_params'], str) else cfg['val_params']

            try:
                module = importlib.import_module(module_name)
                vst_class = getattr(module, class_name)
                self.vsts[vst_type] = vst_class(params)
                print(f"✅ VST Loaded: {vst_type} ({class_name})")
            except Exception as e:
                print(f"❌ Failed to load {vst_type}: {e}")

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"🌐 Connected to Hub ({BROKER_ADDR}) as {SYS_ID}")
            client.subscribe(f"wildlink/{SYS_ID}/cmd")
        else:
            print(f"❌ Connection failed with code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            cmd_id = payload.get("cmd_id")
            
            # 1. Ack
            if cmd_id:
                self.client.publish(f"wildlink/{SYS_ID}/res", json.dumps({
                    "cmd_id": cmd_id, "val_status": "ack", "sys_time": datetime.now().isoformat()
                }))

            # 2. Command Execution
            results = {}
            for target_vst, cmd_data in payload.items():
                if target_vst in self.vsts:
                    res = self.vsts[target_vst].update(cmd_data)
                    results[target_vst] = res
            
            # 3. Success Report
            if results:
                if cmd_id:
                    results["cmd_id"] = cmd_id
                    results["val_status"] = "success"
                self.client.publish(f"wildlink/{SYS_ID}/res", json.dumps(results))
        except Exception as e:
            print(f"❌ Msg Error: {e}")

    def run(self):
        try:
            print(f"📡 Attempting to connect to {BROKER_ADDR}...")
            self.client.connect(BROKER_ADDR, 1883, 60)
            self.client.loop_start()

            while True:
                combined_report = {}
                for name, vst in self.vsts.items():
                    combined_report[name] = vst.update()
                self.client.publish(f"wildlink/{SYS_ID}/res", json.dumps(combined_report))
                time.sleep(10)
        except Exception as e:
            print(f"🔥 Runtime Error: {e}")
        finally:
            self.client.disconnect()

if __name__ == "__main__":
    manager = WildLinkMainManager()
    
    # ここも本来は起動時に一度Hubへ問い合わせるのが理想ですが、一旦テスト用
    initial_config = [
        {"vst_type": "camera", "vst_module": "vst_camera", "vst_class": "VSTCamera", "val_params": "{}"},
        {"vst_type": "sys_monitor", "vst_module": "vst_sys_monitor", "vst_class": "VSTSysMonitor", "val_params": "{}"}
    ]
    
    manager.load_vsts_from_config(initial_config)
    manager.run()