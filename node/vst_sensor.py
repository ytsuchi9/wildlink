import RPi.GPIO as GPIO
import time
from datetime import datetime

class VST_Sensor:
    def __init__(self, role, params, mqtt, on_event):
        self.role = role
        self.params = params
        self.mqtt = mqtt
        self.on_event = on_event
        self.hw_pin = params.get('hw_pin', 18)
        self.interval = params.get('val_interval', 5)
        self.last_detect_time = 0

        GPIO.setmode(GPIO.BCM)
        # センサーはプルダウンまたはプルアップなし（センサー側が出力するため）
        GPIO.setup(self.hw_pin, GPIO.IN) 
        print(f"✅ VST_Sensor (RPi.GPIO) initialized on Pin {self.hw_pin}")

    def poll(self):
        # センサーがHIGH(1)を返しているかチェック
        if GPIO.input(self.hw_pin) == GPIO.HIGH:
            current_time = time.time()
            if current_time - self.last_detect_time > self.interval:
                self.on_detect()
                self.last_detect_time = current_time

    def on_detect(self):
        now_str = datetime.now().isoformat()
        topic = f"node/status/{self.role}"
        if self.mqtt:
            payload = {"vst_type": self.role, "val_status": "detected", "env_time": now_str}
            self.mqtt.publish(topic, payload)

        # 報告
        self.on_event(self.role, "motion_detected")
        print(f"📡 Sent motion to {topic}")

    def stop(self):
        pass