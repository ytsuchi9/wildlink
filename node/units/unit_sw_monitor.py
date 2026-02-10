import RPi.GPIO as GPIO

class WildLinkUnit:
    """物理スイッチ監視ユニット"""
    def __init__(self, config):
        self.val_name = config.get("val_name", "shutdown_button")
        self.hw_pin = config.get("hw_pin", 26)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.hw_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.log_msg = "Monitoring"

    def update(self):
        # ボタンが押されたら(Low)何かアクションを起こす枠組み
        if GPIO.input(self.hw_pin) == GPIO.LOW:
            print("Button Pressed!") # ここに将来のロジックを追加可能
            return {"act_line": True}
        return {}