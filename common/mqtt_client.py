import paho.mqtt.client as mqtt
import json

class MQTTClient:
    def __init__(self, broker_address, client_id):
        self.broker = broker_address
        self.client_id = client_id
        self.on_command_callback = None  # コマンド受信時に呼び出す外部関数
        
        # --- Paho MQTT バージョン互換性の維持 ---
        try:
            # Paho MQTT v2.0+ 
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id)
        except AttributeError:
            # Paho MQTT v1.x 
            self.client = mqtt.Client(client_id)
        
        # 内部イベントハンドラの設定
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def set_on_command_callback(self, callback):
        """
        コマンド受信時に実行したい関数を登録する
        callback(role, payload) の形式を期待
        """
        self.on_command_callback = callback

    def _on_connect(self, client, userdata, flags, rc):
        """接続完了時の処理"""
        if rc == 0:
            print(f"[MQTT] Connected to {self.broker}")
        else:
            print(f"[MQTT] Connection failed with code {rc}")

    def _on_message(self, client, userdata, msg):
        """
        WES 2026 準拠: 受信したトピックから Role を抽出してディスパッチする
        Topic: nodes/{sys_id}/{role}/cmd
        """
        try:
            # トピックを分割して role を特定 (3番目の要素)
            # 例: "nodes/node_001/log_sys/cmd" -> ["nodes", "node_001", "log_sys", "cmd"]
            parts = msg.topic.split('/')
            if len(parts) < 4:
                return # 構造が違う場合は無視

            role = parts[2] 
            payload = json.loads(msg.payload.decode('utf-8'))

            print(f"[MQTT] Received command for Role: {role}")

            # 登録されたコールバックがあれば実行
            if self.on_command_callback:
                self.on_command_callback(role, payload)

        except Exception as e:
            print(f"[MQTT] Error parsing message: {e}")

    def connect(self):
        """ブローカーへ接続し、ループを開始する"""
        try:
            self.client.connect(self.broker, 1883, 60)
            self.client.loop_start()
            return True
        except Exception as e:
            print(f"MQTT Connection Error: {e}")
            return False

    def subscribe_commands(self, sys_id):
        """
        WES 2026 準拠: 自分のノード宛の全役割のコマンドを一括購読
        """
        topic = f"nodes/{sys_id}/+/cmd"
        self.client.subscribe(topic)
        print(f"[MQTT] Subscribed to {topic}")

    def publish_event(self, sys_id, role, data):
        """WES 2026 準拠: イベントトピックへ送信 (Node -> Server/Browser)"""
        topic = f"nodes/{sys_id}/{role}/event"
        return self.publish(topic, data)

    def publish_env(self, sys_id, role, data):
        """WES 2026 準拠: 環境データトピックへ送信 (Node -> DB)"""
        topic = f"nodes/{sys_id}/{role}/env"
        return self.publish(topic, data)

    def publish_res(self, sys_id, role, cmd_id, cmd_status, val_status="acknowledged", log_msg=""):
        """
        WES 2026 準拠: コマンドに対する応答 (ACK/結果) を送信する
        Hub側の `acked_at` や `completed_at` を更新させるための必須メソッド
        """
        topic = f"nodes/{sys_id}/{role}/res"
        data = {
            "ref_cmd_id": cmd_id,
            "cmd_status": cmd_status,  # "acknowledged" か "completed" を期待
            "val_status": val_status,
            "log_msg": log_msg
        }
        return self.publish(topic, data)

    def publish(self, topic, data):
        """汎用的なパブリッシュ（データをJSONに変換）"""
        payload = json.dumps(data, ensure_ascii=False)
        result = self.client.publish(topic, payload)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def disconnect(self):
        """接続解除"""
        self.client.loop_stop()
        self.client.disconnect()
        print("[MQTT] Disconnected")