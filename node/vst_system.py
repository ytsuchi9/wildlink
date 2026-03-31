import os
import sys
import subprocess
import psutil
import time
from common.vst_base import WildLinkVSTBase
from common.logger_config import get_logger

logger = get_logger("vst_system")

class VST_System(WildLinkVSTBase):
    """
    WildLink Event Standard (WES) 2026 準拠
    システム管理 VST ユニット。
    OSレベルの操作（再起動など）や、システムリソースの監視を担当する。
    """
    def __init__(self, sys_id, role, params, mqtt_client=None, event_callback=None):
        super().__init__(sys_id, role, params, mqtt_client, event_callback)
        
        # システムメトリクスの収集間隔（秒）
        self.val_interval = params.get("val_interval", 60)
        self.last_metrics_time = 0
        
        # 状態初期化
        self.sys_cpu_t = 0.0
        self.sys_cpu_u = 0.0
        self.sys_mem_u = 0.0
        self.sys_disk_u = 0.0
        self.sys_uptime = 0

    def control(self, payload):
        """
        システム操作コマンドの実行
        WES 2026: action に基づいて OS コマンドを実行する
        """
        # 基底クラスで共通処理（ref_cmd_id の保持など）
        super().control(payload)
        
        action = payload.get("action")
        cmd_id = payload.get("ref_cmd_id")

        if action == "reboot":
            logger.warning(f"⚠️ [System] Rebooting system by command {cmd_id}")
            if cmd_id:
                self.db.finalize_command(cmd_id, "completed", log_msg="System reboot initiated")
            # 実行猶予を持たせて再起動
            os.system("sudo shutdown -r +1 'Reboot command received via WildLink'")
            
        elif action == "shutdown":
            logger.warning(f"⚠️ [System] Shutting down system by command {cmd_id}")
            if cmd_id:
                self.db.finalize_command(cmd_id, "completed", log_msg="System shutdown initiated")
            os.system("sudo shutdown -h +1 'Shutdown command received via WildLink'")

        elif action == "reload":
            # MainManager側でもトラップしているが、ユニット側でもログを出す
            logger.info(f"🔄 [System] Reloading manager configuration...")
            if cmd_id:
                self.db.finalize_command(cmd_id, "completed", log_msg="Reload initiated")
            # リロード自体は MainManager のループが load_and_init_units を呼ぶことで完結する

        else:
            # 未知のアクション
            if cmd_id:
                self.db.finalize_command(cmd_id, "error", log_msg=f"Unknown action: {action}", log_code=400)

    def poll(self):
        """
        システムメトリクスの定期収集と報告
        """
        now = time.time()
        if now - self.last_metrics_time < self.val_interval:
            return

        try:
            # CPU温度 (Raspberry Pi 特有のパス、または psutil)
            try:
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    self.sys_cpu_t = float(f.read()) / 1000.0
            except:
                self.sys_cpu_t = 0.0

            # リソース使用率
            self.sys_cpu_u = psutil.cpu_percent()
            self.sys_mem_u = psutil.virtual_memory().percent
            self.sys_disk_u = psutil.disk_usage('/').percent
            
            # アップタイム（秒）
            with open('/proc/uptime', 'r') as f:
                self.sys_uptime = int(float(f.readline().split()[0]))

            # ステータス更新（DB/MQTT）
            status_payload = {
                "val_status": "online",
                "sys_cpu_t": round(self.sys_cpu_t, 1),
                "sys_cpu_u": round(self.sys_cpu_u, 1),
                "sys_mem_u": round(self.sys_mem_u, 1),
                "sys_disk_u": round(self.sys_disk_u, 1),
                "sys_up": self.sys_uptime
            }
            
            # WES 2026: node_status_current への書き込みと MQTT 発信
            self.update_status(status_payload)
            
            logger.debug(f"📊 [System Metrics] CPU:{self.sys_cpu_t}°C, Load:{self.sys_cpu_u}%")
            
        except Exception as e:
            logger.error(f"❌ Failed to collect system metrics: {e}")

        self.last_metrics_time = now

    def stop(self):
        """終了時のクリーンアップ"""
        logger.info(f"Stopping {self.role_name} unit.")