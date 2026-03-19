import time
import json
import socket
import paho.mqtt.client as mqtt
from common.db_bridge import DBBridge
from common.wmp_core import WMPHeader

# --- 設定 ---
SYS_ID = "node_001"      # テスト対象のノード
#ROLE = "cam_main"        # テストする役割
ROLE = "rec_main"        # テストする役割
HUB_IP = "127.0.0.1"     # wmp_stream_rx が動いているIP
UDP_PORT = 5005          # 送信先ポート
MQTT_BROKER = "127.0.0.1"

def run_full_test():
    db = DBBridge()
    print(f"🚀 [1/4] DB設定の初期化: {ROLE}...")
    # node_configs にテスト用設定を入れる
    val_params = {"net_port": UDP_PORT, "hub_ip": HUB_IP, "val_res": "320x240"}
    db.save_node_config(SYS_ID, ROLE, "CSI_CAM", val_params)
    
    print(f"📡 [2/4] MQTTコマンド発行: {ROLE} を 'start' に...")
    client = mqtt.Client()
    client.connect(MQTT_BROKER)
    command = {
        "cmd_id": 999,
        "role": ROLE,
        "action": "start",
        "act_run": True
    }
    client.publish(f"wildlink/{SYS_ID}/vst_cmd", json.dumps(command))
    client.disconnect()
    
    print(f"🖼️ [3/4] ダミー画像パケット送信 (WMP経由)...")
    # 適当なバイナリデータ（JPEGのヘッダー FFD8...FFD9 を模した空データ）
    dummy_jpeg = b"\xff\xd8" + b"\x00" * 1000 + b"\xff\xd9"
    
    wmp = WMPHeader(node_id=SYS_ID, media_type=2)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # 5回ほどパケットを投げて RX 側のバッファを埋める
    for i in range(5):
        wmp.send_large_data(sock, (HUB_IP, UDP_PORT), dummy_jpeg)
        print(f"  > Packet {i+1} sent to {HUB_IP}:{UDP_PORT}")
        time.sleep(0.1)
    
    print(f"✅ [4/4] 送信完了。")
    print(f"\n👉 次を確認してください:")
    print(f"1. wmp_stream_rx.py のログに 'Streaming started' が出ているか")
    print(f"2. ブラウザで http://{HUB_IP}:8080/stream/{ROLE} にアクセスして接続できるか")

if __name__ == "__main__":
    run_full_test()