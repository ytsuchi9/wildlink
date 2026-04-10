import time
import subprocess
import os
from common.vst_base import WildLinkVSTBase

class VST_Logger(WildLinkVSTBase):
    """
    WildLink Event Standard (WES) 2026 準拠
    役割: システムログ(journalctl)やアプリケーションログを取得し、MQTTの 'env' トピックへ流す。
    """

    def __init__(self, sys_id, role, params, mqtt_client=None, event_callback=None):
        super().__init__(sys_id, role, params, mqtt_client, event_callback)
        
        # --- Logger専用の設定 ---
        # 取得対象のコマンド (デフォルトは直近10行のシステムログ)
        self.val_log_cmd = params.get("val_log_cmd", "journalctl -n 10 --no-pager")
        # 動作モード: "polling" または "kick"
        self.val_mode = params.get("val_mode", "kick")
        # 定期実行の間隔 (秒)
        self.val_interval = params.get("val_interval", 60)
        
        self.last_poll_time = 0
        self.log_msg = f"Logger unit [{role}] ready in {self.val_mode} mode."

    def execute_logic(self, payload):
        """
        外部からの命令（act_runなど）を処理する
        """
        # act_run=True が送られてきたら、即座にログを収集して送信する
        if payload.get("act_run") is True:
            self.val_status = "processing"
            self.send_event("log_collection_started")
            
            self._fetch_and_send_logs()
            
            self.val_status = "idle"
            self.act_run = False # 実行後はFalseに戻す
            self.send_event("log_collection_finished")

    def poll(self):
        """
        MainManagerから周期的に呼ばれる。
        pollingモードの場合、指定間隔ごとにログを送信する。
        """
        if not self.val_enabled or self.val_mode != "polling":
            return

        now = time.time()
        if now - self.last_poll_time >= self.val_interval:
            self.last_poll_time = now
            self._fetch_and_send_logs()

    def _fetch_and_send_logs(self):
        """
        実際にログを取得し、MQTTの 'env' トピック（生データ用）へパブリッシュする
        """
        try:
            # 外部コマンドを実行してログを取得
            # shell=True は柔軟なコマンド指定のため(パイプ等)。信頼できるDB設定が前提。
            result = subprocess.check_output(self.val_log_cmd, shell=True, stderr=subprocess.STDOUT)
            log_text = result.decode('utf-8')
            
            # WES 2026 命名規則に基づいたデータ構造
            log_data = {
                "log_level": "info",
                "log_msg": "Log fragment retrieved",
                "log_ext": log_text,  # ログの本文を拡張フィールドに格納
                "sys_uptime": self._get_uptime() # ついでに稼働時間も入れるなどの拡張が可能
            }
            
            # 基底クラスのメソッドを使用して {MQTT_PREFIX}/{GROUP_ID}/{sys_id}/{role}/env へ送信
            self.send_data(log_data)
            
            self.log_code = 200
            self.log_msg = "Successfully fetched logs."

        except subprocess.CalledProcessError as e:
            self.log_code = 500
            self.log_msg = f"Log fetch failed: {e.output.decode() if e.output else str(e)}"
            self.send_event("error")
        except Exception as e:
            self.log_code = 500
            self.log_msg = f"Unexpected error in logger: {str(e)}"
            self.send_event("error")

    def _get_uptime(self):
        """システムの稼働時間を取得するヘルパー(例)"""
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
                return int(uptime_seconds)
        except:
            return 0

# MainManagerからの動的生成用
VST_Class = VST_Logger