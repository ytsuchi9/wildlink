import paho.mqtt.client as mqtt
import json

class MQTTClient:
    def __init__(self, broker_address, client_id):
        self.broker = broker_address
        self.client_id = client_id
        
        # --- 修正の核心 ---
        # 以前の self.client = mqtt.Client(client_id) は削除しました
        try:
            # Paho MQTT v2.0+ の書き方
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id)
        except AttributeError:
            # Paho MQTT v1.x (古いOS/ライブラリ) の書き方
            self.client = mqtt.Client(client_id)
        # ------------------

    def connect(self):
        try:
            self.client.connect(self.broker, 1883, 60)
            self.client.loop_start()
            return True
        except Exception as e:
            print(f"MQTT Connection Error: {e}")
            return False

    def publish(self, topic, data):
        """データをJSONに変換して送信"""
        payload = json.dumps(data)
        result = self.client.publish(topic, payload)
        # result.rc == 0 なら成功
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()