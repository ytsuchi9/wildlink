import RPi.GPIO as GPIO
import time
from datetime import datetime
from common.vst_base import WildLinkVSTBase
from common.logger_config import get_logger

logger = get_logger("vst_motion")

class VST_Motion(WildLinkVSTBase):
    def __init__(self, **kwargs):
        """初期化：GPIOピンの設定と初期パラメータのロード"""
        # 🌟 これにより vst_base の __init__ が動き、bootイベントも送信されます
        super().__init__(**kwargs)
        
        # 物理設定 (hw_) と 動作設定 (val_, act_) の読み込み
        # 物理設定の読み込み（vst_baseが setattr してくれているはずですが、型変換が必要なものだけ残す）
        self.hw_pin = int(self.params.get('hw_addr', self.params.get('hw_pin', 18)))
        self.val_interval = float(self.params.get('val_interval', 15.0))
        # 🌟 UIからのON/OFFを制御するための内部フラグ
        self.val_enabled = (int(self.params.get('val_enabled', 1)) == 1)

        # self.act_rec = (int(self.params.get('act_rec', 0)) == 1)
        
        # 🌟 修正: コメントアウトを外し、初期値を明示的にセット（poll時のクラッシュ防止）
        self.env_last_detect_time = 0.0

        try: 
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.hw_pin, GPIO.IN)
        except Exception as e:
            logger.error(f"❌ GPIO Setup Error: {e}")
        logger.info(f"🏃 [{self.role}] Initialized on GPIO {self.hw_pin} (Enabled: {self.val_enabled})")
   
    def poll(self):
        """定期処理：GPIOの監視と状態遷移"""
        # 🌟 UIから無効化(val_enabled=0)されている場合は、センサー監視をスキップ
        if not self.val_enabled:
            return

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
        """動体検知時の処理"""
        # 1. まず自身の状態変数を更新する
        self.val_status = "detected"
        
        # 2. 最新の状態をスナップショット（vst_baseのメソッドを活用）
        current_params = self.get_vst_params()

        # 3. DBステータスを更新 (log_extに全パラメータを渡す)
        self.update_status(
            val_status="detected", 
            log_code=201, 
            log_ext=current_params  # 🌟 ここを修正
        )
        
        iso_time = datetime.now().isoformat()
        
        # 4. Hubへのイベント送信 (Hub側での各種アクション発動判定用)
        # 🌟 act_rec_mode の評価 (1:検知時のみ, 2:状態変化すべて)
        act_db_flag = 1 if getattr(self, 'act_rec_mode', 0) in [1, 2] else 0
        
        # 🌟 is_observation=True で送り、生データをスリム化する
        self.send_event("motion_detected", {
            "env_last_detect": iso_time,
            "act_db": act_db_flag,
            "act_rec": 1 if getattr(self, 'act_rec', 0) else 0,
            "act_line": 1 if getattr(self, 'act_line', 0) else 0
        }, is_observation=True)

    def execute_logic(self, data):
        """WES 2026: 設定パッチの動的適用と完全状態の返却"""
        try:
            cmd_id = data.get('cmd_id')
            if cmd_id:
                self.send_response("acknowledged", log_msg="Config update received.")
            
            # 1. パッチ適用 (cmd_jsonの内容を自身の属性へ自動反映)
            updated_keys = []
            for key, value in data.items():
                # 🌟 sys_ もパッチで書き換えられるように追加 (sys_log_level対応)
                if hasattr(self, key) and key.startswith(('val_', 'act_', 'sys_')):
                    # 🌟 修正: 既存の属性の「型」を取得し、安全にキャスト（変換）して代入する
                    current_val = getattr(self, key)
                    expected_type = type(current_val)
                    
                    try:
                        if isinstance(current_val, bool):
                            # bool型の場合は特別処理 (1, "1", "true" などを True に)
                            new_val = str(value).lower() in ['1', 'true', 'yes']
                        else:
                            # 既存の型（int, float, strなど）に合わせてキャスト
                            new_val = expected_type(value)
                            
                        setattr(self, key, new_val)
                        updated_keys.append(key)
                    except ValueError:
                        logger.warning(f"⚠️ Type casting failed for {key}: expected {expected_type}, got {value}")

            logger.info(f"⚙️ [{self.role}] Patched: {', '.join(updated_keys)}")

            # 2. 全パラメータの抽出 (UIと同期するための log_ext を生成)
            current_params = {
                k: v for k, v in vars(self).items() 
                if k.startswith(('val_', 'act_', 'env_', 'sys_'))
            }

            # 3. 完了報告 (これがMQTT経由でUIに届き、画面が更新される)
            self.send_response(
                "completed", 
                log_msg=f"Configuration patched: {', '.join(updated_keys)}",
                log_code=200,
                log_ext=current_params 
            )
            return True 

        except Exception as e:
            logger.error(f"❌ Error in execute_logic: {e}")
            self.send_response("error", log_msg=str(e), log_code=500)
            return False

    def on_idle_reset(self):
        self.update_status(val_status="idle", log_code=200)

        # 🌟 act_rec_mode が 2(状態変化すべて) の時だけ DB保存指示を出す
        act_db_flag = 1 if getattr(self, 'act_rec_mode', 0) == 2 else 0

        self.send_event("status_changed", {
            "log_time": datetime.now().isoformat(),
            "act_db": act_db_flag
        }, is_observation=True)
        
        logger.debug(f"ℹ️ [{self.role}] Reset to idle")

    def stop(self):
        try: GPIO.cleanup(self.hw_pin)
        except: pass
        super().stop()
        logger.info(f"🛑 [{self.role}] Stopped.")