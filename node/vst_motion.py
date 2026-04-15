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
        WES 2026 準拠: 設定パッチの動的適用と log_ext による全状態報告
        """
        try:
            # 🌟 [WES 2026 儀式] まず受領を報告して acked_at を確定させる
            cmd_id = data.get('cmd_id')
            if cmd_id:
                self.send_response("acknowledged", log_msg="Config update received.")
            # 1. パッチの適用 (cmd_jsonの内容を自身の属性へ自動反映)
            # data に含まれるキーのうち、規約(val_, act_)に合致するもののみを上書き
            updated_keys = []
            for key, value in data.items():
                if hasattr(self, key) and key.startswith(('val_', 'act_')):
                    # 型の整合性を保つための簡易変換 (1/0 -> True/False)
                    if isinstance(getattr(self, key), bool) and not isinstance(value, bool):
                        value = (int(value) == 1)
                    
                    setattr(self, key, value)
                    updated_keys.append(key)

            logger.info(f"⚙️ [{self.role}] Patched: {', '.join(updated_keys)}")

            # 2. 現在の全パラメータを抽出 (データの器：log_ext の生成)
            # 自身の属性から val_, act_, env_ で始まるものを全て集める
            current_params = {
                k: v for k, v in vars(self).items() 
                if k.startswith(('val_', 'act_', 'env_'))
            }

            # 3. 完了報告 (Hub側のDB: node_configs と node_status_current を同時に更新させる)
            self.send_response(
                "completed", 
                log_msg=f"Configuration patched: {', '.join(updated_keys)}",
                log_code=200,
                log_ext=current_params # これがそのままDBの全項目を同期する「器」になる
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