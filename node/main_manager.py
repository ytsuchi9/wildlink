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
MQTT_PREFIX = getattr(config_loader, 'MQTT_PREFIX', 'wildlink')
GROUP_ID    = getattr(config_loader, 'GROUP_ID', 'home_internal')

class MainManager:
    """
    WildLink Event Standard (WES) 2026 準拠
    ノード内の全 VST ユニットを管理し、MQTT命令の配送とユニット間連動を制御。
    """
    def __init__(self):
        self.sys_id = SYS_ID
        self.db = DBBridge()
        self.mqtt = None
        self.units = {}           # 稼働中の VST インスタンス
        self.links = []           # VST間の連動設定
        self.active_timers = {}   # 連動用オフタイマー
        self.running = True
        self._stopping = False    # 2重停止防止フラグ
        
        self.current_config_raw = ""
        self.last_sync_time = 0
        self.sync_interval = 30   # DBとの同期間隔

        self.config_cache_path = os.path.join(current_dir, 'last_config.json')

        # config_loader から取得した HUB_IP を保持
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
            # 自ノード宛の全役割コマンドを購読 ({MQTT_PREFIX}/{GROUP_ID}/{sys_id}/+/cmd)
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
        ユニットから発生したイベントを処理
        """
        payload = payload or {}
        # WES 2026: 共通プレフィックス log_code 等が payload に含まれていることを期待
        
        # MQTTでHubに通知
        msg_type = "res" if event_type in ["result", "completed", "failed"] else "event"
        pub_topic = f"{MQTT_PREFIX}/{GROUP_ID}/{self.sys_id}/{source_role}/{msg_type}"
        self.mqtt.publish(pub_topic, json.dumps(payload))

        # 連動設定の実行
        matched_links = [l for l in self.links if l['source_role'] == source_role and l.get('event_type') == event_type]
        for link in matched_links:
            # [WES 2026 条項20] リンク動作時は lnk_[id] 名義でステータスを更新する運用を推奨
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

    def sync_status_records(self, configs):
        """
        [WES 2026 条項19] 起動・更新時、activeなユニットのレコードが 
        node_status_current に存在することを保証する
        """
        for cfg in configs:
            role = cfg['vst_role_name']
            # INSERT IGNORE により、存在しない場合のみ初期値 'idle' で作成
            self.db.execute(
                "INSERT IGNORE INTO node_status_current (sys_id, vst_role_name, val_status, log_code) VALUES (%s, %s, 'idle', 200)",
                (self.sys_id, role)
            )

    def load_and_init_units(self):
        """DBから設定を取得し、ユニットの生成・破棄を差分で行う"""
        try:
            configs = self.db.fetch_node_config(self.sys_id)
            links = self.db.fetch_vst_links(self.sys_id)
            
            # WES 2026: ステータステーブルの同期
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
        role = cfg['vst_role_name']
        vst_class_name = cfg['vst_class']
        module_name = cfg.get('vst_module') or f"vst_{vst_class_name.lower()}"
        
        params = cfg.get('val_params', {})
        
        # --- [WES 2026 追加項目] 共通情報の注入 ---
        params.update({
            'hw_driver': cfg.get('hw_driver'),
            'hw_bus': cfg.get('hw_bus'),
            'hw_addr': cfg.get('hw_bus_addr'),
            'net_hub_ip': self.hub_ip  # VSTユニットが配信先を知るために注入
        })

        try:
            module = importlib.import_module(f"node.{module_name}")
            importlib.reload(module)
            vst_class = getattr(module, f"VST_{vst_class_name}")

            # 🌟 修正: 新しいインスタンスを作る【前】に、古いユニットを完全に停止（cleanup）させる
            if role in self.units:
                logger.info(f"🔄 Replacing old unit: {role}")
                self.units[role].stop()
                time.sleep(0.1) # ハードウェア解放のための微小な猶予

            # その後で新しいインスタンスを生成する
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

    # ---------------------------------------------------------
    # メインループ
    # ---------------------------------------------------------

    def run(self):
        """起動シーケンス"""
        # --- 信号ハンドラの設定 ---
        # Systemd や Ctrl+C の信号を self.stop で受け取るようにする
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

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
        except Exception as e:
            logger.error(f"🔥 Main loop error: {e}")
        finally:
            self.stop() # 念のため最後に呼ぶ（2重実行はフラグで防止される）

    def stop(self, signum=None, frame=None):
        """停止処理（信号ハンドラとしても動作）"""
        if self._stopping:
            return # すでに停止中なら無視
        self._stopping = True
        
        self.running = False
        logger.info(f"🛑 Shutting down Manager and Units... (Signal: {signum})")
        
        for unit_name, unit in self.units.items():
            try:
                unit.stop()
            except Exception as e:
                # role_name がないユニット(VST_Systemなど)でもエラーで落ちないようにする
                # r_name = getattr(unit, 'role_name', unit_name)
                r_name = getattr(unit, 'role', unit_name)
                logger.error(f"Error stopping unit {r_name}: {e}")
        
        if self.mqtt:
            try: self.mqtt.disconnect()
            except: pass

        # GPIO の安全な後片付け
        try:
            if GPIO and GPIO.getmode() is not None:
                GPIO.cleanup()
                logger.info("🔌 GPIO cleaned up.")
        except:
            pass

        logger.info("👋 Shutdown complete.")
        # sys.exit(0) は不要（runのwhileが抜けるため）

if __name__ == "__main__":
    MainManager().run()