import sys
import os
import json
import time
import threading
import importlib
import signal

# パス解決
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

from common.config_loader import SYS_ID
from common.db_bridge import DBBridge
from common.mqtt_client import MQTTClient
from common.logger_config import get_logger
from common import config_loader

logger = get_logger("main_manager")

class MainManager:
    """
    WildLink Event Standard (WES) 2026 準拠
    ノード内の全 VST ユニットを管理し、MQTT命令の配送とユニット間連動を制御。
    """
    def __init__(self):
        self.sys_id = SYS_ID
        self.db = DBBridge()
        self.mqtt = None
        self.units = {}           # 稼働中の VST インスタンス {role_name: instance}
        self.links = []           # VST間の連動設定
        self.active_timers = {}   # 連動用オフタイマー
        self.running = True
        
        self.current_config_raw = ""
        self.last_sync_time = 0
        self.sync_interval = 30   # DBとの同期間隔
        
        self.config_cache_path = os.path.join(current_dir, 'last_config.json')

        self.hub_ip = config_loader.HUB_IP
        
        # 終了シグナルのトラップ
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    # ---------------------------------------------------------
    # MQTT 命令制御 (Dispatch)
    # ---------------------------------------------------------

    def setup_mqtt(self):
        host = os.getenv('MQTT_BROKER') or "localhost"
        self.mqtt = MQTTClient(host, self.sys_id)
        self.mqtt.set_on_command_callback(self.on_mqtt_command)

        if self.mqtt.connect():
            # 自ノード宛の全役割コマンドを購読 (nodes/{sys_id}/+/cmd)
            self.mqtt.subscribe_commands(self.sys_id)
            logger.info(f"📡 MQTT Connected for {self.sys_id}")

    def on_mqtt_command(self, role, payload):
        """
        Hub Manager からの命令を受信し、適切な VST ユニットへ配送する
        """
        try:
            cmd_id = payload.get("cmd_id") or payload.get("ref_cmd_id", 0)
            
            # 1. 受信確認 (ACK) を即座に返信
            # 物理状態 (val_status) も添えて現在の状況を報告
            if cmd_id:
                current_val = getattr(self.units.get(role), 'val_status', 'idle')
                self.mqtt.publish_res(
                    sys_id=self.sys_id,
                    role=role,
                    cmd_id=cmd_id,
                    cmd_status="acknowledged",
                    val_status=current_val,
                    log_msg=f"Node {self.sys_id} received command."
                )

            # 2. マネージャー自身へのコマンド (reload など)
            if role in ["manager", "system"]:
                if payload.get("action") == "reload":
                    self.load_and_init_units()
                    return

            # 3. ユニットへの配送
            if role in self.units:
                logger.info(f"📩 [Dispatch] -> {role}: {payload.get('action') or payload}")
                self.units[role].control(payload)
            else:
                logger.warning(f"⚠️ Target unit '{role}' not found.")

        except Exception as e:
            logger.error(f"❌ Command Error: {e}")

    # ---------------------------------------------------------
    # イベント・連動制御 (Linkage)
    # ---------------------------------------------------------

    def on_vst_event(self, source_role, event_type, payload=None):
        """
        ユニットから発生したイベントを処理する。
        1. MQTTでHubに通知 (Forwarding)
        2. ノード内の他ユニットを動かす (Linkage)
        """
        payload = payload or {}
        cmd_id = payload.get("ref_cmd_id") or payload.get("cmd_id", 0)
        
        # WES 2026: 命令の結果なら 'res'、自律的な変化なら 'event' トピックへ
        msg_type = "res" if event_type in ["result", "completed", "failed"] else "event"
        pub_topic = f"nodes/{self.sys_id}/{source_role}/{msg_type}"
        
        # ペイロードの整備
        payload["event"] = event_type
        if cmd_id: payload["ref_cmd_id"] = cmd_id

        self.mqtt.publish(pub_topic, json.dumps(payload))
        logger.info(f"🔔 [Event] {source_role}:{event_type} -> {pub_topic}")

        # 連動設定 (vst_links) のチェックと実行
        matched_links = [l for l in self.links if l['source_role'] == source_role and l.get('event_type') == event_type]
        for link in matched_links:
            self.execute_link(link)

    def execute_link(self, link):
        """ノード内連動ロジック。例：人感センサー反応 -> カメラ撮影開始"""
        target_role = link['target_role']
        duration = link.get('val_interval', 0)
        
        if target_role in self.units:
            logger.info(f"➡️ [Link] {link['source_role']} trigger -> {target_role} (for {duration}s)")
            # 内部命令として control を叩く
            self.units[target_role].control({"act_run": True, "ref_cmd_id": 0})
            
            # タイマー設定（一定時間後に停止）
            if duration > 0:
                if target_role in self.active_timers:
                    self.active_timers[target_role].cancel()
                
                t = threading.Timer(duration, self._timer_stop_callback, args=[target_role])
                self.active_timers[target_role] = t
                t.start()

    def _timer_stop_callback(self, role):
        if role in self.units:
            logger.info(f"⏰ [Timer] Stopping {role} (duration expired)")
            self.units[role].control({"act_run": False, "ref_cmd_id": 0})

    # ---------------------------------------------------------
    # ユニットライフサイクル管理
    # ---------------------------------------------------------

    def load_and_init_units(self):
        """DBから設定を取得し、ユニットの生成・破棄を差分で行う"""
        try:
            configs = self.db.fetch_node_config(self.sys_id)
            links = self.db.fetch_vst_links(self.sys_id)
        except Exception:
            logger.error("❌ DB Offline. Using configuration cache.")
            return # 本来はここでキャッシュ読み込み処理

        # 構成の変更をチェック (簡易ハッシュ比較)
        new_config_raw = json.dumps(configs, sort_keys=True, default=str)
        if new_config_raw == self.current_config_raw:
            return 
        
        logger.info("🔄 Configuration change detected. Re-initializing units...")
        self.current_config_raw = new_config_raw
        self.links = links

        # 既存ユニットのうち、設定から消えたものを停止・削除
        active_roles = [c['vst_role_name'] for c in configs]
        for role in list(self.units.keys()):
            if role not in active_roles:
                logger.info(f"🗑️ Removing unit: {role}")
                self.units[role].stop()
                del self.units[role]

        # 各ユニットの起動・更新
        for cfg in configs:
            self._activate_unit(cfg)

    def _activate_unit(self, cfg):
        role = cfg['vst_role_name']
        vst_class_name = cfg['vst_class']
        # vst_camera.py 等のファイル名を特定
        module_name = cfg.get('vst_module') or f"vst_{vst_class_name.lower()}"
        
        params = cfg.get('val_params', {})
        # 追加ハードウェア情報を注入
        params.update({
            'hw_driver': cfg.get('hw_driver'),
            'hw_bus': cfg.get('hw_bus'),
            'hw_addr': cfg.get('hw_bus_addr')
        })

        try:
            # 動的インポート
            module = importlib.import_module(f"node.{module_name}")
            importlib.reload(module)
            vst_class = getattr(module, f"VST_{vst_class_name}")

            # インスタンス生成
            instance = vst_class(
                sys_id=self.sys_id,
                role=role,
                params=params,
                mqtt_client=self.mqtt,
                event_callback=self.on_vst_event
            )
            
            if role in self.units: self.units[role].stop()
            self.units[role] = instance
            logger.info(f"✅ Unit Activated: {role} ({vst_class_name})")
            
        except Exception as e:
            logger.error(f"❌ Failed to activate {role}: {e}")

    # ---------------------------------------------------------
    # メインループ
    # ---------------------------------------------------------

    def run(self):
        """起動シーケンス"""
        logger.info(f"🚀 MainManager starting... (ID: {self.sys_id})")
        self.setup_mqtt()
        
        # 💡 [重要] 起動時ステータスリセット
        # 前回の異常終了などで DB に残っている「streaming」などの状態をリセット
        try:
            self.db.update_node_status(self.sys_id, None, {"val_status": "idle", "log_msg": "System Boot"})
            logger.info("🧹 Initial status reset completed.")
        except Exception as e:
            logger.warning(f"Status reset skipped: {e}")

        self.load_and_init_units()
        
        try:
            while self.running:
                now = time.time()
                # 各ユニットの定期処理実行
                for unit in list(self.units.values()):
                    try: unit.poll()
                    except: pass

                # 定期的な死活監視と設定同期
                if now - self.last_sync_time > self.sync_interval:
                    self.db.update_node_heartbeat(self.sys_id, "online")
                    self.load_and_init_units()
                    self.last_sync_time = now

                time.sleep(0.1)
        finally:
            self.stop()

    def stop(self, signum=None, frame=None):
        self.running = False
        logger.info("🛑 Shutting down Manager and Units...")
        for unit in self.units.values():
            try: unit.stop()
            except: pass
        if self.mqtt: self.mqtt.disconnect()
        if GPIO: GPIO.cleanup()
        logger.info("👋 Shutdown complete.")

if __name__ == "__main__":
    MainManager().run()