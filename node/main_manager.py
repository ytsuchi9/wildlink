import sys
import os
import json
import time
import requests
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# 自作ユニットのインポート
from vst_camera import VSTCamera

class MainManager:
    def __init__(self):
        # --- .env の場所を特定（スクリプトの1階層上を探す） ---
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        env_path = os.path.join(parent_dir, '.env')
        
        print(f"[*] Looking for .env at: {env_path}") # デバッグ用

        if os.path.exists(env_path):
            load_dotenv(env_path)
            print("[+] .env file loaded successfully.")
        else:
            print("[!] .env file NOT FOUND. Using fallback defaults.")

        # --- 設定の反映 ---
        self.node_id = os.getenv("SYS_ID", "node_000")
        self.hub_ip = os.getenv("HUB_IP", "127.0.0.1")
        self.mqtt_port = int(os.getenv("MQTT_PORT", 1883))
        
        # --- パス設定 ---
        self.config_url = f"http://{self.hub_ip}/get_node_config.php?node_id={self.node_id}"
        self.local_config_path = os.path.join(os.path.dirname(__file__), "local_config.json")
        
        self.units = {}
        self.sys_status = "initializing"
        
        # --- MQTT設定 ---
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        
        # --- 起動シーケンス ---
        self.setup()

    def load_config(self):
        """PHP APIから設定を取得し、キャッシュを更新する"""
        print(f"[*] Fetching config from {self.config_url}...")
        try:
            response = requests.get(self.config_url, timeout=5)
            if response.status_code == 200:
                config_data = response.json()
                # ローカルファイルに保存（生存モード用）
                with open(self.local_config_path, "w") as f:
                    json.dump(config_data, f, indent=4)
                print("[+] Config updated from Hub.")
                return config_data
        except Exception as e:
            print(f"[!] Hub connection failed: {e}")

        # 失敗した場合はローカルキャッシュを読み込む
        if os.path.exists(self.local_config_path):
            print("[!] Using local cached config.")
            with open(self.local_config_path, "r") as f:
                return json.load(f)
        
        print("[!!!] No config available. Check network or local cache.")
        return []

    def setup(self):
        """ユニットの初期化とMQTT接続"""
        configs = self.load_config()
        print(f"DEBUG: Received configs: {configs}")
        
        for conf in configs:
            vst_type = conf.get('vst_type')
            vst_class = conf.get('vst_class', '') # PHP修正後にここが入る
            params = conf.get('val_params', {})
            enabled = conf.get('val_enabled', 1)

            if not enabled:
                continue

            # カテゴリを小文字にして比較（揺れを防止）
            cls_lower = vst_class.lower()

            # Cameraカテゴリの初期化
            if cls_lower == 'camera':
                unit = VSTCamera(cam_type=vst_type, node_id=self.node_id)
                unit.val_res = params.get('val_res', '320x240')
                unit.val_fps = params.get('val_fps', 5)
                self.units[vst_type] = unit
                print(f"[+] Unit Registered: {vst_type} (Camera)")

            # Sensorカテゴリの初期化（将来用）
            elif cls_lower == 'sensor':
                # 今は登録のみ（ここに対応するクラスができたら追加）
                print(f"[+] Unit Registered: {vst_type} (Sensor)")

            # Actuatorカテゴリの初期化（将来用）
            elif cls_lower == 'actuator':
                print(f"[+] Unit Registered: {vst_type} (Actuator)")

        # MQTT接続
        try:
            self.mqtt_client.connect(self.hub_ip, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
            self.sys_status = "running"
        except Exception as e:
            print(f"[!] MQTT connection failed: {e}")

    def on_connect(self, client, userdata, flags, rc):
        print(f"[*] Connected to Broker ({self.hub_ip}) with result code {rc}")
        # 「vst/node_001/cmd/」以下のトピックをすべて購読する
        client.subscribe(f"vst/{self.node_id}/cmd/#")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            target = payload.get("hw_target")
            
            if target in self.units:
                print(f"[*] Command for {target}: {payload}")
                self.units[target].control(payload)
            else:
                print(f"[?] Target {target} unknown or not initialized.")
        except Exception as e:
            print(f"[!] Message Error: {e}")

    def publish_status(self):
        """現在の全ユニットの状態を統合してパブリッシュ"""
        status_data = {
            "sys_id": self.node_id,
            "sys_status": self.sys_status,
            "units": {}
        }
        for name, unit in self.units.items():
            status_data["units"][name] = {
                "val_status": unit.val_status,
                "log_code": unit.log_code
            }
        
        self.mqtt_client.publish(f"vst/{self.node_id}/state/sys", json.dumps(status_data))

    def run(self):
        print(f"[*] MainManager ({self.node_id}) is running...")
        try:
            while True:
                self.publish_status()
                time.sleep(5) 
        except KeyboardInterrupt:
            print("[*] Stopping units...")
            for unit in self.units.values():
                if hasattr(unit, 'stop_streaming'):
                    unit.stop_streaming()
            self.mqtt_client.loop_stop()

if __name__ == "__main__":
    manager = MainManager()
    manager.run()