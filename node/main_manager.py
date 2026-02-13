import sys
import os

# --- 共通パスの追加 ---
# 1. 自分の場所を取得 (/opt/wildlink/node)
current_dir = os.path.dirname(os.path.abspath(__file__))
# 2. 親の場所を取得 (/opt/wildlink)
wildlink_root = os.path.dirname(current_dir)
# 3. common と node 自身をパスに追加
sys.path.append(os.path.join(wildlink_root, "common"))
sys.path.append(current_dir) # units フォルダを見つけるため

# パスを通した後にインポートする
import time
import json
import paho.mqtt.client as mqtt
from units.unit_camera_v1 import WildLinkUnit as CameraVST

# 「動的ロード」部分の予習
import importlib

# --- 設定 ---
NODE_ID = "node_001"
MQTT_HOST = "192.168.0.102" # Hub(Pi 2)のIP
TOPIC_CMD = f"wildlink/{NODE_ID}/cmd"
TOPIC_RES = f"wildlink/{NODE_ID}/res"

# 「動的ロード」部分の予習
def load_vst_units(config_list):
    loaded_units = []
    for cfg in config_list:
        # 例: vst_type が "camera" なら units.unit_camera_v1 を探す
        module_path = f"units.unit_{cfg['vst_type']}_v1"
        module = importlib.import_module(module_path)
        
        # クラス (WildLinkUnit) をインスタンス化
        vst_class = getattr(module, cfg['vst_class'])
        instance = vst_class(cfg['val_params'])
        loaded_units.append(instance)
    return loaded_units

# 命令を保持する一時バッファ
current_commands = {}

# --- MQTT コールバック ---
def on_message(client, userdata, msg):
    global current_commands
    try:
        payload = json.loads(msg.payload.decode())
        current_commands.update(payload)
        print(f"[*] Received Command: {payload}")
    except Exception as e:
        print(f"Error parsing MQTT: {e}")

# --- メインロジック ---
def main():
    client = mqtt.Client()
    client.on_message = on_message
    client.connect(MQTT_HOST, 1883, 60)
    client.subscribe(TOPIC_CMD)
    client.loop_start()

    # 1. 本来はDBから取得するが、まずは手動でVSTをリスト化
    # 今後はここを動的にインポート・生成する仕組みにします
    vst_units = [
        CameraVST({"sys_id": NODE_ID, "val_name": "FrontCamera", "hw_pin": "/dev/video0"})
    ]

    print(f"🚀 WildLink Manager [{NODE_ID}] started.")

    try:
        while True:
            all_reports = {}
            
            for unit in vst_units:
                # VSTの更新 (命令を渡し、状態を受け取る)
                report = unit.update(current_commands)
                all_reports[unit.val_name] = report

            # 状態をMQTTでHubへ報告
            client.publish(TOPIC_RES, json.dumps(all_reports))
            
            # 命令バッファをクリア (1回実行したら忘れる)
            current_commands.clear()
            
            time.sleep(1) # 1秒周期でループ

    except KeyboardInterrupt:
        print("Stopping Manager...")
        client.loop_stop()

if __name__ == "__main__":
    main()