import paho.mqtt.client as mqtt
import json
import time
import os
from dotenv import load_dotenv
from vst_camera import VSTCamera

load_dotenv()

class MainManager:
    def __init__(self):
        self.sys_status = "initializing"
        
        # ユニット初期化
        self.vst_cam_pi = VSTCamera(cam_type="pi", node_id="pi0_csi")
        self.vst_cam_usb = VSTCamera(cam_type="usb", node_id="pi0_usb")
        
        self.broker = os.getenv("MQTT_BROKER", "localhost")
        self.base_topic = os.getenv("MQTT_BASE_TOPIC", "vst/pi0")
        
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "vst_pi0_manager")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc, properties):
        print(f"[log_msg] Connected to Broker: {self.broker}")
        self.client.subscribe(f"{self.base_topic}/cmd/#")
        self.sys_status = "running"

    def on_message(self, client, userdata, msg):
        try:
            target = msg.topic.split('/')[-1]
            payload = json.loads(msg.payload.decode())
            
            # B案: 全てのカメラ命令は 'cam' トピックで受け取り、hw_targetで振り分け
            if target == "cam":
                self.vst_cam_pi.control(payload)
                self.vst_cam_usb.control(payload)
                
        except Exception as e:
            print(f"[log_code] MQTT Error: {e}")

    def report_status(self):
        """定期報告に log_code (エラー内容) を含める"""
        status = {
            "sys_status": self.sys_status,
            "cam_pi": {
                "val_status": self.vst_cam_pi.val_status,
                "log_msg": self.vst_cam_pi.log_msg,
                "log_code": self.vst_cam_pi.log_code
            },
            "cam_usb": {
                "val_status": self.vst_cam_usb.val_status,
                "log_msg": self.vst_cam_usb.log_msg,
                "log_code": self.vst_cam_usb.log_code
            }
        }
        self.client.publish(f"{self.base_topic}/state/sys", json.dumps(status))

    def run(self):
        self.client.connect(self.broker, 1883, 60)
        self.client.loop_start()
        try:
            while True:
                self.report_status()
                time.sleep(10)
        except KeyboardInterrupt:
            self.vst_cam_pi.stop_streaming()
            self.vst_cam_usb.stop_streaming()
            self.client.loop_stop()

if __name__ == "__main__":
    manager = MainManager()
    manager.run()