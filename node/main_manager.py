import sys
import os
import json
import time
import threading
import importlib
import signal

# --- フェーズ1: パス解決と.envの確実な読み込み ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(project_root, ".env"))
except ImportError:
    pass

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
MQTT_PREFIX = getattr(config_loader, 'MQTT_PREFIX', 'wildlink')
GROUP_ID    = getattr(config_loader, 'GROUP_ID', 'home_internal')

class MainManager:
    """
    WildLink Event Standard (WES) 2026 準拠
    ノード内の全 VST ユニットを管理し、MQTT命令の配送とユニット間連動を制御。
    """
    def __init__(self):
        """初期化：各種マネージャー変数やフラグのセットアップを行います。"""
        self.sys_id = SYS_ID
        self.db = DBBridge()
        self.mqtt = None
        self.units = {}
        self.links = []
        self.active_timers = {}
        self.running = True
        self._stopping = False
        
        self.current_config_raw = ""
        self.last_sync_time = 0
        self.sync_interval = 30

        self.config_cache_path = os.path.join(current_dir, 'last_config.json')
        self.hub_ip = config_loader.HUB_IP
        
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    def setup_mqtt(self):
        """MQTTクライアントを初期化し、Hubからの命令購読を開始します。"""
        host = os.getenv('MQTT_BROKER') or "localhost"
        self.mqtt = MQTTClient(host, self.sys_id)
        self.mqtt.set_on_command_callback(self.on_mqtt_command)

        if self.mqtt.connect():
            self.mqtt.subscribe_commands(self.sys_id)
            logger.info(f"📡 MQTT Connected for {self.sys_id}")

    def on_mqtt_command(self, role, payload):
        """Hub Manager からの命令を受信し、対象となるVSTユニットのcontrolへ配送します。"""
        try:
            cmd_id = payload.get("cmd_id") or payload.get("ref_cmd_id", 0)
            
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

            if role in ["manager", "system"]:
                if payload.get("action") == "reload":
                    self.load_and_init_units()
                    return

            if role in self.units:
                logger.info(f"📩 [Dispatch] -> {role}: {payload.get('action') or payload}")
                self.units[role].control(payload)
            else:
                logger.warning(f"⚠️ Target unit '{role}' not found.")

        except Exception as e:
            logger.error(f"❌ Command Error: {e}")

    def on_vst_event(self, source_role, event_type, payload=None):
        """ユニットから発生したイベント（完了やエラー等）を処理し、Hubへ通知または連動を実行します。"""
        payload = payload or {}
        
        msg_type = "res" if event_type in ["result", "completed", "failed"] else "event"
        pub_topic = f"{MQTT_PREFIX}/{GROUP_ID}/{self.sys_id}/{source_role}/{msg_type}"
        self.mqtt.publish(pub_topic, json.dumps(payload))

        matched_links = [l for l in self.links if l['source_role'] == source_role and l.get('event_type') == event_type]
        for link in matched_links:
            self.execute_link(link)

    def execute_link(self, link):
        """VST間の連動設定（例：センサー感知でカメラ起動など）を実行します。"""
        target_role = link['target_role']
        duration = link.get('val_interval', 0)
        
        if target_role in self.units:
            logger.info(f"➡️ [Link] {link['source_role']} trigger -> {target_role} (for {duration}s)")
            self.units[target_role].control({"act_run": True, "ref_cmd_id": 0})
            
            if duration > 0:
                if target_role in self.active_timers:
                    self.active_timers[target_role].cancel()
                
                t = threading.Timer(duration, self._timer_stop_callback, args=[target_role])
                self.active_timers[target_role] = t
                t.start()

    def _timer_stop_callback(self, role):
        """連動タイマー満了時に対象ユニットを停止させるコールバックです。"""
        if role in self.units:
            logger.info(f"⏰ [Timer] Stopping {role} (duration expired)")
            self.units[role].control({"act_run": False, "ref_cmd_id": 0})

    def sync_status_records(self, configs):
        """起動・更新時に、DBの node_status_current テーブルにノード状態の初期レコードを作成します。"""
        for cfg in configs:
            role = cfg['vst_role_name']
            self.db.execute(
                "INSERT IGNORE INTO node_status_current (sys_id, vst_role_name, val_status, log_code) VALUES (%s, %s, 'idle', 200)",
                (self.sys_id, role)
            )

    def load_and_init_units(self):
        """DBから最新設定を取得し、ユニットの生成・破棄を差分比較して反映します。"""
        try:
            configs = self.db.fetch_node_config(self.sys_id)
            links = self.db.fetch_vst_links(self.sys_id)
            self.sync_status_records(configs)
        except Exception as e:
            logger.error(f"❌ DB Access Error: {e}")
            return 

        new_config_raw = json.dumps(configs, sort_keys=True, default=str)
        if new_config_raw == self.current_config_raw:
            return 
        
        logger.info("🔄 Configuration change detected. Re-initializing units...")
        self.current_config_raw = new_config_raw
        self.links = links

        active_roles = [c['vst_role_name'] for c in configs]
        for role in list(self.units.keys()):
            if role not in active_roles:
                logger.info(f"🗑️ Removing unit: {role}")
                self.units[role].stop()
                del self.units[role]

        for cfg in configs:
            self._activate_unit(cfg)

    def _activate_unit(self, cfg):
        """DB設定に基づき、特定のVSTユニット（クラス）を動的にロードしてインスタンス化します。"""
        role = cfg['vst_role_name']
        vst_class_name = cfg['vst_class']
        module_name = cfg.get('vst_module') or f"vst_{vst_class_name.lower()}"
        
        params = cfg.get('val_params', {})
        params.update({
            'hw_driver': cfg.get('hw_driver'),
            'hw_bus': cfg.get('hw_bus'),
            'hw_addr': cfg.get('hw_bus_addr'),
            'net_hub_ip': self.hub_ip
        })

        try:
            module = importlib.import_module(f"node.{module_name}")
            importlib.reload(module)
            vst_class = getattr(module, f"VST_{vst_class_name}")

            if role in self.units:
                logger.info(f"🔄 Replacing old unit: {role}")
                self.units[role].stop()
                time.sleep(0.1)

            instance = vst_class(
                sys_id=self.sys_id,
                role=role,
                params=params,
                mqtt_client=self.mqtt,
                event_callback=self.on_vst_event
            )
            
            self.units[role] = instance
            logger.info(f"✅ Unit Activated: {role} ({vst_class_name}) @ HUB:{self.hub_ip}")
            
        except Exception as e:
            logger.error(f"❌ Failed to activate {role}: {e}")

    def run(self):
        """ノードのメインループ。MQTT起動、DB状態リセット、ユニットのポーリング実行を管理します。"""
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

        logger.info(f"🚀 MainManager starting... (ID: {self.sys_id})")
        self.setup_mqtt()
        
        try:
            self.db.update_node_status(self.sys_id, None, {"val_status": "idle", "log_msg": "System Boot"})
            logger.info("🧹 Initial status reset completed.")
        except Exception as e:
            logger.warning(f"Status reset skipped: {e}")

        self.load_and_init_units()
        
        try:
            while self.running:
                now = time.time()
                for unit in list(self.units.values()):
                    try: unit.poll()
                    except: pass

                if now - self.last_sync_time > self.sync_interval:
                    self.db.update_node_heartbeat(self.sys_id, "online")
                    self.load_and_init_units()
                    self.last_sync_time = now

                time.sleep(0.1)
        except Exception as e:
            logger.error(f"🔥 Main loop error: {e}")
        finally:
            # フェーズ1: 異常終了時も必ずstop処理を呼び出し、リソースを解放する
            self.stop() 

    def stop(self, signum=None, frame=None):
        """終了処理（信号ハンドラ）。稼働中の全ユニットを安全に停止し、GPIOやMQTTを開放します。"""
        if self._stopping:
            return 
        self._stopping = True
        
        self.running = False
        logger.info(f"🛑 Shutting down Manager and Units... (Signal: {signum})")
        
        for unit_name, unit in self.units.items():
            try:
                unit.stop()
            except Exception as e:
                r_name = getattr(unit, 'role', unit_name)
                logger.error(f"Error stopping unit {r_name}: {e}")
        
        if self.mqtt:
            try: self.mqtt.disconnect()
            except: pass

        try:
            if GPIO and GPIO.getmode() is not None:
                GPIO.cleanup()
                logger.info("🔌 GPIO cleaned up.")
        except:
            pass

        logger.info("👋 Shutdown complete.")

if __name__ == "__main__":
    MainManager().run()