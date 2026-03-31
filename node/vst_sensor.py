import RPi.GPIO as GPIO
import time
from datetime import datetime
from common.vst_base import WildLinkVSTBase

class VST_Sensor(WildLinkVSTBase):
    def __init__(self, **kwargs):
        # 親クラスの初期化にすべての引数を渡す必要があります
        super().__init__(**kwargs)
    #def __init__(self, sys_id, role, params, mqtt_client=None, event_callback=None):
    #    super().__init__(sys_id, role, params, mqtt_client, event_callback)
        self.role = role
        self.params = params
        self.mqtt = mqtt
        self.on_event = on_event
        
        self.hw_pin = params.get('hw_pin', 18)
        if config and config.get("hw_bus_addr"):
            try:
                self.hw_pin = int(config["hw_bus_addr"])
            except: pass

        GPIO.setup(self.hw_pin, GPIO.IN) 
        self.interval = params.get('val_interval', 5)
        self.last_detect_time = 0
        print(f"🏃 VST_Sensor [{self.role}] initialized on Pin {self.hw_pin}")

    def poll(self):
        if GPIO.input(self.hw_pin) == GPIO.HIGH:
            current_time = time.time()
            if current_time - self.last_detect_time > self.interval:
                self.on_detect()
                self.last_detect_time = current_time

    def on_detect(self):
        # 💡 event_type を vst_links の 'motion' と一致させる
        if self.on_event:
            self.on_event(self.role, "motion")
        
        if self.mqtt:
            topic = f"node/status/{self.role}"
            payload = {"vst_type": self.role, "val_status": "detected"}
            self.mqtt.publish(topic, payload)