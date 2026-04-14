import RPi.GPIO as GPIO
import time
from datetime import datetime
from common.vst_base import WildLinkVSTBase
from common.logger_config import get_logger

logger = get_logger("vst_motion")

class VST_Motion(WildLinkVSTBase):
    def __init__(self, **kwargs):
        """初期化：GPIOピンの設定と入力モード(プルダウン等なしのシンプル構成)のセットアップを行います。"""
        super().__init__(**kwargs)
        
        self.hw_pin = int(self.params.get('hw_addr', self.params.get('hw_pin', 18)))
        self.val_interval = float(self.params.get('val_interval', 15.0))
        
        self.env_last_detect_time = 0

        try: GPIO.setmode(GPIO.BCM)
        except: pass
        GPIO.setup(self.hw_pin, GPIO.IN)
        
        logger.info(f"🏃 [{self.role}] Initialized on GPIO {self.hw_pin} (Interval: {self.val_interval}s)")
    
    def poll(self):
        """メインループから呼ばれる定期処理。GPIOピンの状態を確認し、検知/待機状態を判定します。"""
        is_high = (GPIO.input(self.hw_pin) == GPIO.HIGH)
        now = time.time()

        if is_high:
            if self.val_status != "detected":
                logger.info(f"🔔 [{self.role}] Motion Detected!")
                self.on_detect()
            
            self.env_last_detect_time = now
        else:
            if self.val_status == "detected" and (now - self.env_last_detect_time) > self.val_interval:
                self.on_idle_reset()

    def on_detect(self):
        """動体検知時の処理。DBステータスを更新し、MQTTでイベントをブロードキャストします。"""
        self.update_status(val_status="detected", log_code=201, log_ext={"msg": "Motion signal high"})
        
        iso_time = datetime.now().isoformat()
        self.send_event("motion_detected", {"env_last_detect": iso_time})

    def execute_logic(self, data):
        """
        Hubからのコマンド受信時の実処理。
        設定変更（intervalや録画フラグ等）を受け取り、自身のパラメータを更新します。
        """
        try:
            if "val_enabled" in data:
                self.val_enabled = (int(data["val_enabled"]) == 1)
            if "val_interval" in data:
                self.val_interval = float(data["val_interval"])
            if "act_rec" in data:
                self.act_rec = (int(data["act_rec"]) == 1)
                
            logger.info(f"⚙️ [{self.role}] Configuration patched: {data}")

            self.update_status(val_status=self.val_status, log_code=200)

            # 更新後のパラメータを結果としてHubへ返す
            res_payload = {
                "val_enabled": 1 if self.val_enabled else 0,
                "val_interval": self.val_interval,
                "act_rec": 1 if self.act_rec else 0
            }
            
            self.send_response(
                "completed", 
                log_msg="Configuration updated successfully",
                log_code=200,
                log_ext={"val_res_payload": res_payload} 
            )

            return True 

        except Exception as e:
            logger.error(f"❌ Error in execute_logic: {e}")
            self.send_response("error", log_msg=str(e), log_code=500)
            return False

    def on_idle_reset(self):
        """インターバル経過後、待機状態(idle)に戻す処理。"""
        self.update_status(val_status="idle", log_code=200)
        self.send_event("status_changed", {"log_time": datetime.now().isoformat()})
        logger.debug(f"ℹ️ [{self.role}] Reset to idle")

    def stop(self):
        """終了処理。対象のGPIOピンを開放し、基底クラスの停止処理を呼びます。"""
        try: GPIO.cleanup(self.hw_pin)
        except: pass
        super().stop()
        logger.info(f"🛑 [{self.role}] Stopped.")