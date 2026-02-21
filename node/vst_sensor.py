import time
from datetime import datetime
from gpiozero import MotionSensor

class VST_Sensor:
    def __init__(self, role, params, mqtt):
        self.role = role
        self.params = params
        self.mqtt = mqtt
        
        # ドライバーの選択
        driver_type = params.get('hw_driver', 'SR501')
        self.device = GenericPIR(params)

        self.last_detect_time = 0
        self.interval = params.get('val_interval', 5)

    def poll(self):
        if self.device and self.device.is_detected():
            current_time = time.time()
            if current_time - self.last_detect_time > self.interval:
                self.on_detect()
                self.last_detect_time = current_time

    def on_detect(self):
        now_str = datetime.now().isoformat()
        topic = f"node/status/{self.role}"
        
        if self.mqtt:
            payload = {
                "vst_type": self.role,
                "val_status": "detected",
                "env_time": now_str
            }
            # mqtt_client側でjson.dumpsしてくれるので、そのまま渡す
            self.mqtt.publish(topic, payload)
            print(f"📡 Sent motion to {topic}")

# --- シンプルな gpiozero ドライバー ---

class GenericPIR:
    def __init__(self, params):
        self.pin = params.get('hw_pin', 4)
        try:
            # pin_factoryを指定せず、標準の仕組み（RPi.GPIOなど）を使用
            # queue_len=1 にすることで、検知のタイムラグを最小限にします
            self.sensor = MotionSensor(self.pin, pull_up=False, queue_len=1)
            print(f"✅ GenericPIR initialized on Pin {self.pin} (Standard mode)")
        except Exception as e:
            print(f"❌ Failed to initialize GenericPIR: {e}")
            self.sensor = None
        
    def is_detected(self):
        if self.sensor:
            return self.sensor.motion_detected
        return False