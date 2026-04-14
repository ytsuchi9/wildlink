import paho.mqtt.client as mqtt
import os
import sys
import json

# --- フェーズ1: パス解決の強化 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 🌟 どんな環境からも config_loader を確実に見つける
try:
    from common import config_loader
except ImportError:
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    import config_loader

MQTT_PREFIX = getattr(config_loader, 'MQTT_PREFIX', 'wildlink')
GROUP_ID    = getattr(config_loader, 'GROUP_ID', 'home_internal')

class MQTTClient:
    def __init__(self, broker_address, client_id):
        """初期化：Paho MQTTのバージョンに合わせたクライアント生成を行います。"""
        self.broker = broker_address
        self.client_id = client_id
        self.on_command_callback = None  
        
        # --- Paho MQTT バージョン互換性の維持 ---
        try:
            # Paho MQTT v2.0+ 
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id)
        except AttributeError:
            # Paho MQTT v1.x 
            self.client = mqtt.Client(client_id)
        
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def set_on_command_callback(self, callback):
        """
        コマンド受信時に実行したい関数を登録する
        callback(role, payload) の形式を期待
        """
        self.on_command_callback = callback

    def _on_connect(self, client, userdata, flags, rc):
        """[コールバック] 接続完了時の処理"""
        if rc == 0:
            print(f"[MQTT] Connected to {self.broker}")
        else:
            print(f"[MQTT] Connection failed with code {rc}")

    def _on_message(self, client, userdata, msg):
        """
        [コールバック] 受信したトピックから Role を抽出してディスパッチする
        Topic: {MQTT_PREFIX}/{GROUP_ID}/{sys_id}/{role}/cmd
        """
        try:
            parts = msg.topic.split('/')
            if len(parts) < 4:
                return 

            role = parts[3] 
            payload = json.loads(msg.payload.decode('utf-8'))

            print(f"[MQTT] Received command for Role: {role}")

            if self.on_command_callback:
                self.on_command_callback(role, payload)

        except Exception as e:
            print(f"[MQTT] Error parsing message: {e}")

    def connect(self):
        """ブローカーへ接続し、非同期のネットワークループを開始する"""
        try:
            self.client.connect(self.broker, 1883, 60)
            self.client.loop_start()
            return True
        except Exception as e:
            print(f"MQTT Connection Error: {e}")
            return False

    def subscribe_commands(self, sys_id):
        """指定したノード宛ての全コマンドトピック(cmd)を一括購読する"""
        topic = f"{MQTT_PREFIX}/{GROUP_ID}/{sys_id}/+/cmd"
        self.client.subscribe(topic)
        print(f"[MQTT] Subscribed to {topic}")

    def publish_event(self, sys_id, role, data):
        """イベントトピック(/event)へデータを送信する"""
        topic = f"{MQTT_PREFIX}/{GROUP_ID}/{sys_id}/{role}/event"
        return self.publish(topic, data)

    def publish_env(self, sys_id, role, data):
        """環境データトピック(/env)へデータを送信する"""
        topic = f"{MQTT_PREFIX}/{GROUP_ID}/{sys_id}/{role}/env"
        return self.publish(topic, data)

    def publish_res(self, sys_id, role, cmd_id, cmd_status, val_status="acknowledged", log_msg=""):
        """
        コマンドに対する応答 (ACK/結果) を /res トピックへ送信する
        Hub側の `acked_at` や `completed_at` を更新させるための必須メソッド
        """
        topic = f"{MQTT_PREFIX}/{GROUP_ID}/{sys_id}/{role}/res"
        data = {
            "ref_cmd_id": cmd_id,
            "cmd_status": cmd_status,  
            "val_status": val_status,
            "log_msg": log_msg
        }
        return self.publish(topic, data)

    def publish(self, topic, data):
        """指定したトピックへJSON形式でデータをパブリッシュする汎用メソッド"""
        payload = json.dumps(data, ensure_ascii=False)
        result = self.client.publish(topic, payload)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def disconnect(self):
        """非同期ループを停止し、ブローカーから切断する"""
        self.client.loop_stop()
        self.client.disconnect()
        print("[MQTT] Disconnected")