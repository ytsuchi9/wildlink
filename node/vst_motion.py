import RPi.GPIO as GPIO
import time
import json
from datetime import datetime
from common.vst_base import WildLinkVSTBase
from common.logger_config import get_logger

# ロガーの初期化
logger = get_logger("vst_motion")

class VST_Motion(WildLinkVSTBase):
    """
    WildLink 2026 | Motion Detection Unit (WES 2026 準拠)
    役割: PIRセンサーの信号変化を監視し、エッジ検出（立ち上がり）によって
         二重検知を防ぎつつ、MQTTブロードキャストおよびDB記録を行う。
    """

    def __init__(self, **kwargs):
        # 親クラス(WildLinkVSTBase)の初期化
        super().__init__(**kwargs)
        
        # --- 1. ハードウェア設定 (物理層) ---
        # 🌟 修正: self.conf ではなく、渡された kwargs を直接参照します
        db_addr = kwargs.get('hw_bus_addr') 
        
        if db_addr and str(db_addr).isdigit():
            self.hw_pin = int(db_addr)
        else:
            # DBに指定がない場合は params 内の指定、それもなければ 18
            self.hw_pin = int(self.params.get('hw_pin', 18))
        
        # --- 2. 動作パラメータ設定 (論理層) ---
        self.interval = float(self.params.get('val_interval', 15.0))
        self.save_db = self.params.get('save_db', False)
        
        # グループ名の設定 (UIとの一致用)
        # 以前の設計に基づき、デフォルトを 'home_internal' に
        self.group_id = kwargs.get('group_id', 'home_internal')
        
        # --- 3. 内部状態管理 ---
        self.last_detect_time = 0
        self.last_state = False
        self.current_status = "idle"

        # GPIOのセットアップ (BCMモード)
        # 注意: setupの前に setmode を呼ぶ必要があります（Baseクラスで呼ばれていない場合）
        try:
            GPIO.setmode(GPIO.BCM)
        except:
            pass # すでに設定済みの場合はスキップ
            
        GPIO.setup(self.hw_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        
        logger.info(f"🏃 [{self.role}] Initialized on GPIO {self.hw_pin} (Group: {self.group_id}, Interval: {self.interval}s)")
    
    def poll(self):
        # 物理信号の読み取り
        is_high = (GPIO.input(self.hw_pin) == GPIO.HIGH)
        now = time.time()

        # 🌟 ロジック：前回の状態がLOWで、今回がHIGH（立ち上がり）の時だけ発火
        if is_high and not self.last_state:
            # 前回の検知（発火）から interval 秒以上経過しているか
            if (now - self.last_detect_time) > self.interval:
                logger.info(f"🔔 [{self.role}] Motion Detected! (Pin {self.hw_pin} went HIGH)")
                self.on_detect()
                self.last_detect_time = now
            else:
                logger.debug(f"⏳ [{self.role}] Ignoring: Within interval.")
        
        # 🌟 状態がHIGHからLOWに戻った時の処理
        if not is_high and self.last_state:
            logger.info(f"ℹ️ [{self.role}] Signal cleared (Pin went LOW)")
            self.on_idle_reset()

        # 今回の状態を記録
        self.last_state = is_high

    def on_detect(self):
        """
        動きを検知（Rising Edge）した際のアクション。
        MQTTパブリッシュ、内部イベント、DB保存を順次実行する。
        """
        self.current_status = "detected"
        timestamp = datetime.now().isoformat()
        
        logger.info(f"🔔 [{self.role}] Motion Detected! (Broadcasting to {self.group_id})")

        # 1. 内部イベントコールバック (Manager層を通じて他のUnit（Cam等）を動かす用)
        if self.on_event:
            self.on_event(self.role, "motion", {"time": timestamp})

        # 2. MQTTペイロード作成 (WES 2026 規格)
        payload = {
            "event": "motion_detected",
            "val_status": "detected",
            "log_code": 201, # 201: Created/Detected
            "log_msg": "Motion signal high",
            "time": int(time.time()),
            "env_last_detect": timestamp,
            "role": self.role # UI側でのコンポーネント特定用
        }
        self.publish_event(payload)

        # 3. DB記録 (save_dbオプションがTrueの時のみ)
        if self.save_db:
            self._record_to_db(payload)

    def on_idle_reset(self):
        """
        センサーが静止状態（Idle）に戻った際の通知。
        UI側のインジケーターを通常色に戻すトリガーになる。
        """
        self.current_status = "idle"
        payload = {
            "event": "status_changed",
            "val_status": "idle",
            "log_code": 200, # 200: OK/Normal
            "time": int(time.time()),
            "role": self.role
        }
        self.publish_event(payload)
        logger.debug(f"ℹ️ [{self.role}] Reset to idle")

    def publish_event(self, payload):
        """
        MQTTメッセージを所定のトピックに送信する。
        Topic構造: wildlink/{group}/{sys_id}/{role}/event
        """
        """
        if self.mqtt:
            topic = f"wildlink/{self.group_id}/{self.sys_id}/{self.role}/event"
            try:
                self.mqtt.publish(topic, json.dumps(payload))
            except Exception as e:
                logger.error(f"❌ [{self.role}] MQTT Publish Error: {e}")
        """
        """トピックを強制的に home_internal に合わせて送信"""
        if self.mqtt:
            # 迷子防止のため、明示的にトピックを組み立てる
            topic = f"wildlink/home_internal/{self.sys_id}/{self.role}/event"
            logger.info(f"📤 [{self.role}] Publishing to {topic}")
            self.mqtt.publish(topic, json.dumps(payload))

    def _record_to_db(self, payload):
        """
        DBBridgeを使用して node_data テーブルに履歴を書き込む。
        """
        try:
            data_patch = {
                "val_status": payload["val_status"],
                "log_code": payload["log_code"],
                "env_last_detect": payload.get("env_last_detect")
            }
            # 基底クラスで self.db が DBBridge インスタンスであることを想定
            if hasattr(self, 'db') and self.db:
                self.db.insert_node_data(self.sys_id, self.role, data_patch)
        except Exception as e:
            logger.error(f"❌ [{self.role}] DB Record Error: {e}")

    def stop(self):
        """
        プログラム終了時のクリーンアップ処理。
        """
        GPIO.cleanup(self.hw_pin)
        logger.info(f"🛑 [{self.role}] Stopped.")