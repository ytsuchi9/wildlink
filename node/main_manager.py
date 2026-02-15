import sys
import os
import time
import json
import importlib
import signal
import paho.mqtt.client as mqtt
from dotenv import load_dotenv # 先にインポート

# --- 最強のパス解決ロジック ---
current_dir = os.path.dirname(os.path.abspath(__file__))
wildlink_root = os.path.dirname(current_dir)
sys.path.append(os.path.join(wildlink_root, "common"))
sys.path.append(current_dir)

# 🔥 ここで先に .env をロードする！
load_dotenv(os.path.join(wildlink_root, ".env"))

# デバッグ用：これでIPが出ればOK
print(f"DEBUG: MQTT_BROKER is {os.getenv('MQTT_BROKER')}")

# その後に土管を呼ぶ
try:
    from db_bridge import DBBridge
    print("✅ Success: DBBridge loaded via 土管.")
except ImportError as e:
    print(f"❌ Error: Could not find db_bridge.py. {e}")
    sys.exit(1)

# --- 設定 ---
NODE_ID = os.getenv('NODE_ID', 'node_001')
MQTT_HOST = os.getenv('MQTT_BROKER')
running = True

def handle_sigint(signum, frame):
    global running
    print("\n[*] Stopping WildLink Manager...")
    running = False

signal.signal(signal.SIGINT, handle_sigint)
signal.signal(signal.SIGTERM, handle_sigint)

def main():
    # 土管の初期化（.envのパスを明示的に渡す）
    bridge = DBBridge(dotenv_path=os.path.join(wildlink_root, ".env"))
    
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(MQTT_HOST, 1883, 60)
    client.loop_start()

    # 土管から設定を取得
    configs = bridge.fetch_node_config(NODE_ID)
    vst_units = []
    
    if configs:
        for cfg in configs:
            try:
                module = importlib.import_module(cfg["vst_module"])
                vst_class = getattr(module, cfg["vst_class"])
                params = json.loads(cfg["val_params"]) if isinstance(cfg["val_params"], str) else cfg["val_params"]
                vst_units.append(vst_class(params))
                print(f"✅ VST Loaded: {cfg['vst_type']}")
            except Exception as e:
                print(f"❌ Failed to load VST {cfg['vst_type']}: {e}")

    print(f"🚀 WildLink Manager [{NODE_ID}] Operational.")

    try:
        while running:
            all_reports = {}
            for unit in vst_units:
                # 本来はここで current_commands を渡すが一旦空で
                report = unit.update({})
                all_reports[unit.val_name] = report
            
            if all_reports:
                client.publish(f"wildlink/{NODE_ID}/res", json.dumps(all_reports))
            
            time.sleep(1)
    finally:
        client.loop_stop()
        client.disconnect()
        print("[*] Cleanup complete. Good night!")

if __name__ == "__main__":
    main()