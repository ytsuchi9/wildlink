# /opt/wildlink/node/vst_sw_monitor.py
import RPi.GPIO as GPIO
from vst_base import WildLinkVSTBase

class VSTSwMonitor(WildLinkVSTBase):
    def __init__(self, config):
        super().__init__(config)
        self.hw_pin = config.get("hw_pin", 26)
        GPIO.setmode(GPIO.BCM)
        # プルアップ/ダウン設定もDBから渡せると最高
        GPIO.setup(self.hw_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def update(self, cmd_dict=None):
        # 物理ボタンの状態を act_ (アクション) として報告
        is_pressed = GPIO.input(self.hw_pin) == GPIO.LOW
        return {
            "act_sw": is_pressed,
            "log_msg": "Button monitoring"
        }