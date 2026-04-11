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
        # 🌟 実行中に DB 設定が変更された場合に備え、
        # 必要に応じて self.params を再読み込みするロジックを検討
        # 現状は起動時に取得した val_interval を使用
        is_high = (GPIO.input(self.hw_pin) == GPIO.HIGH)
        now = time.time()

        if is_high:
            # 検知中の場合はインターバルを無視して「検知中」を維持する
            if self.val_status != "detected":
                logger.info(f"🔔 [{self.role}] Motion Detected!")
                self.on_detect()
            
            # 最終検知時刻は常に更新
            self.env_last_detect_time = now
        else:
            # 信号が LOW になり、かつ設定されたインターバル（秒）が経過したら idle に戻す
            if self.val_status == "detected" and (now - self.env_last_detect_time) > self.val_interval:
                self.on_idle_reset()

    def on_detect(self):
        # 🌟 vst_base の標準機能を使用！
        # 1. DBの status を更新
        self.update_status(val_status="detected", log_code=201, log_ext={"msg": "Motion signal high"})
        
        # 2. Manager経由でMQTT(event)をブロードキャスト（WES2026準拠）
        iso_time = datetime.now().isoformat()
        self.send_event("motion_detected", {"env_last_detect": iso_time})

    def execute_logic(self, data):
        """
        vst_base/main_manager からコマンドを受信した際に呼ばれる実処理
        """
        try:
            # 1. パッチ適用
            if "val_enabled" in data:
                self.val_enabled = (int(data["val_enabled"]) == 1)
            if "val_interval" in data:
                self.val_interval = float(data["val_interval"])
            if "act_rec" in data:
                self.act_rec = (int(data["act_rec"]) == 1)
                
            logger.info(f"⚙️ [{self.role}] Configuration patched: {data}")

            # 2. ステータス更新
            self.update_status(val_status=self.val_status, log_code=200)

            # 3. 完了報告
            # 🌟 ポイント：'val_res_payload' を直接渡さず、'log_ext' の中に入れます
            res_payload = {
                "val_enabled": 1 if self.val_enabled else 0,
                "val_interval": self.val_interval,
                "act_rec": 1 if self.act_rec else 0
            }
            
            self.send_response(
                "completed", 
                log_msg="Configuration updated successfully",
                log_code=200,
                log_ext={"val_res_payload": res_payload}  # 👈 ここに入れる！
            )

            return True # 完了

        except Exception as e:
            logger.error(f"❌ Error in execute_logic: {e}")
            # エラー時も報告を忘れない
            self.send_response("error", log_msg=str(e), log_code=500)
            return False

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