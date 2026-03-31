import RPi.GPIO as GPIO
import time

class VST_Switch:
    # 💡 config引数を受け取れるように拡張
    def __init__(self, sys_id, role, params, mqtt_client=None, event_callback=None):
        super().__init__(sys_id, role, params, mqtt_client, event_callback)
        self.role = role
        self.params = params
        self.mqtt = mqtt
        self.on_event = on_event
        
        # 💡 DBの新しいカラム hw_bus_addr 等からピンを取るロジックに合わせる
        # なければ val_params から取る
        self.hw_pin = params.get("hw_pin", 17)
        if config and config.get("hw_bus_addr"):
            try:
                self.hw_pin = int(config["hw_bus_addr"])
            except: pass
        
        # GPIO設定
        GPIO.setup(self.hw_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.prev_state = GPIO.input(self.hw_pin)
        self.last_debounce_time = 0
        
        print(f"🔘 VST_Switch [{self.role}] initialized on Pin {self.hw_pin}")

    def poll(self):
        current_state = GPIO.input(self.hw_pin)
        if current_state == 0 and self.prev_state == 1:
            now = time.time()
            if now - self.last_debounce_time > 0.3:
                # 💡 event_type を vst_links の 'button' と一致させる
                if self.on_event:
                    self.on_event(self.role, "button") 
                self.last_debounce_time = now
        self.prev_state = current_state

    def stop(self):
        pass