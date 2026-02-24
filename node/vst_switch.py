# /opt/wildlink/node/vst_switch.py

import RPi.GPIO as GPIO
import time

class VST_Switch:
    def __init__(self, role, params, mqtt, on_event):
        self.role = role
        self.params = params
        self.mqtt = mqtt
        self.on_event = on_event
        self.hw_pin = params.get("hw_pin", 17)
        
        # GPIO設定
        GPIO.setwarnings(False) # 警告を抑制
        GPIO.setup(self.hw_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # 前回の状態を保持（プルアップなので初期値は1）
        self.prev_state = GPIO.input(self.hw_pin)
        self.last_debounce_time = 0
        
        print(f"🔘 VST_Switch (High-speed Poll) initialized on Pin {self.hw_pin}")

    def poll(self):
        """MainManagerから0.1秒ごとに呼ばれる"""
        current_state = GPIO.input(self.hw_pin)
        
        # 状態が「1（離）」から「0（押）」に変わった瞬間を捉える
        if current_state == 0 and self.prev_state == 1:
            now = time.time()
            # チャタリング防止（前回の検知から0.3秒以上経過しているか）
            if now - self.last_debounce_time > 0.3:
                print(f"🔘 [Poll] Button pressed on Pin {self.hw_pin}")
                if self.on_event:
                    self.on_event(self.role, "button_pressed")
                self.last_debounce_time = now
        
        self.prev_state = current_state

    def stop(self):
        """リロード時は特に追加処理なし（Managerのcleanupに任せる）"""
        pass