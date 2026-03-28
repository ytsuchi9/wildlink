import sys
import os
import json
import time
import threading
import RPi.GPIO as GPIO

# パス解決
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from common.db_bridge import DBBridge
from common.mqtt_client import MQTTClient
from common.logger_config import get_logger

# ロガー初期化
logger = get_logger("main_manager")

class MainManager:
    """
    WildLink Event Standard (WES) 2026 準拠
    ノード内の全 VST ユニットを統括し、MQTT 命令を Role（役割）ごとに適切にルーティングする司令塔。
    """
    def __init__(self, sys_id):
        self.sys_id = sys_id
        self.logger = get_logger(f"{sys_id}:main_manager")
        self.db = DBBridge()
        self.units = {}
        self.links = []
        self.active_timers = {}
        self.current_config_raw = ""
        self.last_sync_time = 0
        self.sync_interval = 30
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_cache_path = os.path.join(base_dir, 'last_config.json')

    def setup_mqtt(self):
        """MQTT クライアントの初期化とコマンド購読の設定"""
        host = os.getenv('MQTT_BROKER') or "127.0.0.1"
        self.mqtt = MQTTClient(host, self.sys_id)
        
        # WES 2026: コマンド受信時のコールバックを登録
        self.mqtt.set_on_command_callback(self.dispatch_command)
        
        if self.mqtt.connect():
            # WES 2026: 自分のノード宛の全役割のコマンドを一括購読 (nodes/{sys_id}/+/cmd)
            self.mqtt.subscribe_commands(self.sys_id)
            logger.info(f"📡 MQTT Connected & Subscribed to commands for {self.sys_id}")

    def dispatch_command(self, role, payload):
        """
        WES 2026 準拠: 受信したトピックから抽出された Role に基づき、
        適切な VST インスタンスへ処理を振り分ける。
        """
        # 1. マネージャー自身への直接命令 (reload 等)
        if role == "manager" or role == "system":
            action = payload.get("action")
            if action == "reload":
                logger.info("🔄 Reload command received via MQTT")
                self.load_and_init_units()
            return

        # 2. 各 VST ユニットへの命令
        if role in self.units:
            try:
                # 基底クラスの control() を通じて命令を実行
                # ここで cmd_id の紐付けや属性の自動更新が行われる
                self.units[role].control(payload)
            except Exception as e:
                logger.error(f"❌ [{role}] Command execution failed: {e}")
        else:
            logger.warning(f"⚠️ Received command for unknown role: {role}")

    def load_and_init_units(self):
        """DBから設定を読み込み、役割名をキーとしてユニットを生成する (修正版)"""
        new_configs = self.db.fetch_node_config(self.sys_id)
        new_links = self.db.fetch_vst_links(self.sys_id)
        
        # (DB接続失敗時のキャッシュ読み込みロジックは維持)
        if new_configs is None:
            if os.path.exists(self.config_cache_path):
                logger.warning("⚠️ [Manager] DB connection failed. Loading from cache...")
                with open(self.config_cache_path, 'r') as f:
                    cached_data = json.load(f)
                    new_configs = cached_data.get("configs", [])
                    new_links = cached_data.get("links", [])
            else:
                logger.error("❌ [Manager] No config available")
                return

        current_data_set = {"configs": new_configs, "links": new_links}
        new_config_raw = json.dumps(current_data_set, sort_keys=True, default=str)
        
        # 変更がなければ何もしない
        if new_config_raw == self.current_config_raw:
            return

        logger.info("🔄 [Manager] Config/Links change detected. Re-initializing units...")
        self.current_config_raw = new_config_raw
        self.links = new_links
        
        # キャッシュの保存
        with open(self.config_cache_path, 'w') as f:
            json.dump(current_data_set, f)
        
        # 既存リソースの解放
        for t in self.active_timers.values(): t.cancel()
        self.active_timers.clear()
        for unit in self.units.values():
            if hasattr(unit, 'stop'): unit.stop()
        self.units.clear()
        
        GPIO.cleanup()
        GPIO.setmode(GPIO.BCM)

        # ユニットの動的初期化
        for cfg in new_configs:
            vst_type = cfg['vst_type']
            role_name = cfg.get('vst_role_name') or vst_type 
            cls_name = cfg['vst_class']
            mod_name = cfg.get('vst_module', f"vst_{cls_name.lower()}")
            
            # --- 💡 修正ポイント: 文字列ならデコードする ---
            params = cfg.get('val_params', {})
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except:
                    params = {}

            try:
                # 動的インポート
                module = __import__(f"node.{mod_name}", fromlist=[f"VST_{cls_name}"])
                vst_class = getattr(module, f"VST_{cls_name}")
                
                # ユニット初期化
                self.units[role_name] = vst_class(
                    self.sys_id, 
                    role_name, 
                    params,  # ここが辞書型になっている必要がある
                    self.mqtt, 
                    self.on_event
                )
                
                logger.info(f"✅ [{role_name}] Activated (Type: {vst_type})")
            except Exception as e: 
                logger.error(f"❌ [{role_name}] Activation failed: {e}")

    def on_event(self, source_role, event_type):
        """ユニット間で発生した連動設定(Links)の実行"""
        logger.debug(f"🔔 [Event] Source: {source_role} Type: {event_type}")
        
        matched_links = [l for l in self.links if l['source_role'] == source_role and l.get('event_type') == event_type]
        
        for link in matched_links:
            target_role = link['target_role']
            duration = link.get('val_interval', 0)
            
            if target_role in self.units:
                target_unit = self.units[target_role]
                # リンクによる自動制御 (act_run 等をキック)
                is_running = getattr(target_unit, "act_run", False)
                new_state = not is_running if duration == 0 else True
                
                logger.info(f"➡️ [Route] {source_role} -> {target_role} (State: {new_state})")
                target_unit.control({"act_run": new_state})
                
                # タイマー制御の維持
                if target_role in self.active_timers:
                    self.active_timers[target_role].cancel()
                
                if new_state and duration > 0:
                    t = threading.Timer(duration, lambda r=target_role: self.units[r].control({"act_run": False}))
                    t.daemon = True
                    self.active_timers[target_role] = t
                    t.start()

    def run(self):
        """メインループ"""
        self.setup_mqtt()
        self.load_and_init_units()
        
        logger.info(f"📡 Main Manager [{self.sys_id}] is running...")
        try:
            while True:
                now = time.time()
                # 周期的なDB同期
                if now - self.last_sync_time > self.sync_interval:
                    self.db.update_node_heartbeat(self.sys_id, status="online")
                    self.load_and_init_units() 
                    self.last_sync_time = now
                
                # 各ユニットの定期ポーリング (センサー読み取り等)
                for unit in list(self.units.values()):
                    unit.poll()
                
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("👋 Stopping Manager...")
            self.mqtt.disconnect()
            GPIO.cleanup()

if __name__ == "__main__":
    sys_id = os.getenv("SYS_ID", "node_001")
    manager = MainManager(sys_id)
    manager.run()