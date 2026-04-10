import RPi.GPIO as GPIO
import time
from datetime import datetime
from common.vst_base import WildLinkVSTBase
from common.logger_config import get_logger

logger = get_logger("vst_motion")

class VST_Motion(WildLinkVSTBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # params の中に DB からのパラメータが入っている
        self.hw_pin = int(self.params.get('hw_addr', self.params.get('hw_pin', 18)))
        self.val_interval = float(self.params.get('val_interval', 15.0))
        
        self.env_last_detect_time = 0

        # 古いコードの良いとこ取り: プルダウン抵抗を使わずシンプルに設定
        try: GPIO.setmode(GPIO.BCM)
        except: pass
        GPIO.setup(self.hw_pin, GPIO.IN)
        
        logger.info(f"🏃 [{self.role}] Initialized on GPIO {self.hw_pin} (Interval: {self.val_interval}s)")
    
    def poll(self):
        is_high = (GPIO.input(self.hw_pin) == GPIO.HIGH)
        now = time.time()

        if is_high:
            if (now - self.env_last_detect_time) > self.val_interval:
                logger.info(f"🔔 [{self.role}] Motion Detected! (Pin {self.hw_pin} is HIGH)")
                self.on_detect()
                self.env_last_detect_time = now
        else:
            if self.val_status == "detected" and (now - self.env_last_detect_time) > self.val_interval:
                self.on_idle_reset()

    def on_detect(self):
        # 🌟 vst_base の標準機能を使用！
        # 1. DBの status を更新
        self.update_status(val_status="detected", log_code=201, log_ext={"msg": "Motion signal high"})
        
        # 2. Manager経由でMQTT(event)をブロードキャスト（WES2026準拠）
        iso_time = datetime.now().isoformat()
        self.send_event("motion_detected", {"env_last_detect": iso_time})

    def on_idle_reset(self):
        # 🌟 DBステータスを戻し、イベント通知
        self.update_status(val_status="idle", log_code=200)
        self.send_event("status_changed", {"log_time": datetime.now().isoformat()})
        logger.debug(f"ℹ️ [{self.role}] Reset to idle")

    def stop(self):
        # 終了処理（vst_base の stop も呼ぶ）
        try: GPIO.cleanup(self.hw_pin)
        except: pass
        super().stop()
        logger.info(f"🛑 [{self.role}] Stopped.")