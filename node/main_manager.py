import sys
import os
import json
import time
import threading
import importlib
import signal

# パス解決：プロジェクトルートを sys.path に追加
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# RPi.GPIO のインポート (GPIOがない環境への配慮)
try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

from common.db_bridge import DBBridge
from common.mqtt_client import MQTTClient
from common.logger_config import get_logger

logger = get_logger("main_manager")

class MainManager:
    """
    WildLink Event Standard (WES) 2026 準拠
    ノード内の全 VST ユニットを統括し、MQTT 命令のルーティングと
    ユニット間連動 (vst_links) を制御する司令塔。
    """
    def __init__(self):
        self.sys_id = os.getenv("NODE_ID") or os.getenv("SYS_ID") or "node_001"
        self.db = DBBridge()
        self.mqtt = None
        self.units = {}           # 稼働中の VST ユニット {role_name: instance}
        self.links = []           # DB から取得した連動設定
        self.active_timers = {}   # 連動用タイマー {target_role: Timer}
        self.running = True
        
        self.current_config_raw = ""
        self.last_sync_time = 0
        self.sync_interval = 30   # DBとの同期間隔(秒)
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_cache_path = os.path.join(base_dir, 'last_config.json')
        
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    def setup_mqtt(self):
        """MQTT クライアントの初期化"""
        host = os.getenv('MQTT_BROKER') or "127.0.0.1"
        self.mqtt = MQTTClient(host, self.sys_id)
        self.mqtt.set_on_command_callback(self.on_mqtt_command)

        if self.mqtt.connect():
            # 自分のノード宛の全役割のコマンドを一括購読 (nodes/{sys_id}/+/cmd)
            self.mqtt.subscribe_commands(self.sys_id)
            logger.info(f"📡 MQTT Connected & Subscribed for {self.sys_id}")

    def on_mqtt_command(self, role, payload):
        """
        MQTT 命令受信時の処理。
        1. Hubへ「受信確認(ACK)」をMQTTで返信（これによりHub側のacked_atが更新される）
        2. 適切なユニットへ命令を配送する。
        """
        try:
            # ref_cmd_id または cmd_id を取得
            cmd_id = payload.get("ref_cmd_id") or payload.get("cmd_id", 0)
            
            # 【重要】Hubに対して「受け取った」ことをMQTTで即座に返信 (WES 2026 規格)
            # トピック: nodes/{sys_id}/{role}/res
            if cmd_id > 0:
                ack_payload = {
                    "ref_cmd_id": cmd_id,
                    "val_status": "acknowledged",
                    "log_msg": f"Received by {role}"
                }
                res_topic = f"nodes/{self.sys_id}/{role}/res"
                self.mqtt.publish(res_topic, json.dumps(ack_payload))
                logger.info(f"📤 [ACK Sent] Topic: {res_topic} for CMD:{cmd_id}")

            # マネージャー自身への直接命令 (reload 等)
            if role in ["manager", "system"]:
                if payload.get("action") == "reload":
                    logger.info("🔄 Reload command received")
                    self.load_and_init_units()
                    # 完了報告を送信
                    if cmd_id > 0:
                        res_payload = {
                            "ref_cmd_id": cmd_id,
                            "val_status": "success",
                            "log_msg": "Reload completed"
                        }
                        self.mqtt.publish(f"nodes/{self.sys_id}/{role}/res", json.dumps(res_payload))
                return

            # 各 VST ユニットへの命令配送
            if role in self.units:
                logger.info(f"📩 [Dispatch] to {role}: {payload}")
                self.units[role].control(payload)
            else:
                logger.warning(f"⚠️ [Dispatch Failed] Target unit not found: {role}")
                if cmd_id > 0:
                    err_payload = {
                        "ref_cmd_id": cmd_id,
                        "val_status": "error",
                        "log_code": 404,
                        "log_msg": f"Unit {role} is not active on this node"
                    }
                    self.mqtt.publish(f"nodes/{self.sys_id}/{role}/res", json.dumps(err_payload))
                
        except Exception as e:
            logger.error(f"❌ [MQTT Command] Error: {e}")

    def on_vst_event(self, source_role, event_type, payload=None):
        """
        ユニットからのイベント受信時の処理。
        WES 2026: 全てのイベント（および結果報告）はHubに転送する。
        """
        payload = payload or {}
        cmd_id = payload.get("ref_cmd_id") or payload.get("cmd_id", 0)

        # 1. Hubへイベント/レスポンスを転送
        # event_type が 'result' なら /res トピック、それ以外なら /event トピック
        msg_type = "res" if event_type == "result" else "event"
        pub_topic = f"nodes/{self.sys_id}/{source_role}/{msg_type}"
        
        # 必要なメタデータを付与
        payload["event_type"] = event_type
        if cmd_id > 0: payload["ref_cmd_id"] = cmd_id

        self.mqtt.publish(pub_topic, json.dumps(payload))
        logger.info(f"🔔 [Event Forwarded] {source_role}:{event_type} -> {pub_topic}")

        # 2. vst_links に基づくノード内連動
        matched_links = [l for l in self.links if l['source_role'] == source_role and l.get('event_type') == event_type]
        for link in matched_links:
            self.execute_link(link)

    def execute_link(self, link):
        """連動実行ロジック (ノード内完結)"""
        target_role = link['target_role']
        duration = link.get('val_interval', 0)
        
        if target_role in self.units:
            target_unit = self.units[target_role]
            is_running = getattr(target_unit, "act_run", False)
            new_state = not is_running if duration == 0 else True
            
            logger.info(f"➡️ [Link Route] {target_role} ({'START' if new_state else 'STOP'})")
            target_unit.control({"act_run": new_state, "ref_cmd_id": 0})
            
            if target_role in self.active_timers:
                self.active_timers[target_role].cancel()
            
            if new_state and duration > 0:
                t = threading.Timer(duration, self._timer_stop_callback, args=[target_role])
                t.daemon = True
                self.active_timers[target_role] = t
                t.start()

    def _timer_stop_callback(self, role):
        if role in self.units:
            logger.info(f"⏰ [Timer Expired] Stopping {role}")
            self.units[role].control({"act_run": False, "ref_cmd_id": 0})
        if role in self.active_timers:
            del self.active_timers[role]

    def load_and_init_units(self):
        """設定読み込みとユニット初期化"""
        try:
            new_configs = self.db.fetch_node_config(self.sys_id)
            new_links = self.db.fetch_vst_links(self.sys_id)
        except Exception as e:
            logger.error(f"DB access failed: {e}")
            new_configs = None

        if new_configs is None:
            if os.path.exists(self.config_cache_path):
                logger.warning("⚠️ [Manager] DB offline. Loading from cache...")
                with open(self.config_cache_path, 'r') as f:
                    cache = json.load(f)
                    new_configs = cache.get("configs", [])
                    new_links = cache.get("links", [])
            else:
                logger.error("❌ No configuration available.")
                return

        current_data = {"configs": new_configs, "links": new_links}
        new_config_raw = json.dumps(current_data, sort_keys=True, default=str)
        if new_config_raw == self.current_config_raw:
            return

        logger.info("🔄 [Manager] Configuration change detected.")
        self.current_config_raw = new_config_raw
        self.links = new_links
        
        try:
            with open(self.config_cache_path, 'w') as f:
                json.dump(current_data, f)
        except Exception as e: logger.error(f"Cache error: {e}")

        for t in self.active_timers.values(): t.cancel()
        self.active_timers.clear()
        for unit in list(self.units.values()):
            try: unit.stop()
            except: pass
        self.units.clear()

        if GPIO:
            try:
                GPIO.setwarnings(False)
                GPIO.cleanup()
                GPIO.setmode(GPIO.BCM)
            except: pass

        for cfg in new_configs:
            role = cfg['vst_role_name']
            module_name = cfg.get('vst_module') or f"vst_{cfg['vst_class'].lower()}"
            class_name = cfg['vst_class']
            full_class_name = class_name if class_name.startswith("VST_") else f"VST_{class_name}"
            
            params = cfg.get('val_params', {})
            if isinstance(params, str):
                try: params = json.loads(params)
                except: params = {}

            try:
                module_path = f"node.{module_name}"
                module = importlib.import_module(module_path)
                vst_class = getattr(module, full_class_name)
                
                instance = vst_class(
                    sys_id=self.sys_id,
                    role=role,
                    params=params,
                    mqtt_client=self.mqtt,
                    event_callback=self.on_vst_event
                )
                self.units[role] = instance
                logger.info(f"✅ [{role}] Activated")
            except Exception as e:
                logger.error(f"❌ [{role}] Activation failed: {e}")

    def run(self):
        """メインループ"""
        self.setup_mqtt()
        self.load_and_init_units()
        
        try:
            while self.running:
                now = time.time()
                for unit in list(self.units.values()):
                    try: unit.poll()
                    except Exception as e: logger.error(f"Poll error: {e}")

                if now - self.last_sync_time > self.sync_interval:
                    # ハートビート更新
                    self.db.update_node_heartbeat(self.sys_id, "online")
                    self.load_and_init_units()
                    self.last_sync_time = now

                time.sleep(0.1)
        except Exception as e:
            logger.error(f"🔥 Fatal error: {e}")
        finally:
            self.stop()

    def stop(self, signum=None, frame=None):
        self.running = False
        logger.info("🛑 Stopping Manager...")
        for t in self.active_timers.values(): t.cancel()
        for unit in list(self.units.values()):
            try: unit.stop()
            except: pass
        if GPIO:
            try: GPIO.cleanup()
            except: pass
        if self.mqtt:
            self.mqtt.disconnect()

if __name__ == "__main__":
    manager = MainManager()
    manager.run()