import json
import time
from datetime import datetime
from common.db_bridge import DBBridge
from common.logger_config import get_logger

logger = get_logger("vst_base")

class WildLinkVSTBase:
    """
    WildLink Event Standard (WES) 2026 準拠
    すべての WildLink VST (Virtual System Unit) の基底クラス。
    
    [WES 2026 ライフサイクル管理]
    1. control(): コマンドを受信し ref_cmd_id を保持。
    2. send_response("acknowledged"): 「届いた」ことをHub/DBへ即報告 (acked_at)
    3. send_response("completed"): 「完了した」ことをHub/DBへ報告 (completed_at)
    """

    def __init__(self, sys_id, role, params=None, mqtt_client=None, event_callback=None):
        self.sys_id = sys_id
        self.vst_role_name = role 
        self.role = role 
        self.params = params or {}
        self.mqtt = mqtt_client
        self.event_callback = event_callback
        
        self.db = DBBridge()
        
        # --- WES 2026 標準ステータス変数の初期化 ---
        self.val_status = "idle"       # idle/streaming/error/starting
        self.log_code = 200            # ハイブリッドエラーコード (200: OK, 4xx/5xx: Error)
        self.log_ext = {}              # 詳細コンテキスト (JSON辞書)
        self.log_msg = "Initialized"
        
        self.val_enabled = self.params.get("val_enabled", True)
        self.ref_cmd_id = 0            # 処理中のコマンドID（0はアクティブなし）
        
        # 起動時のパラメータ展開
        if isinstance(self.params, dict):
            self.log_ext = self.params.get("log_ext", {})
            for key, value in self.params.items():
                if any(key.startswith(pre) for pre in ["val_", "hw_", "net_"]):
                    setattr(self, key, value)

        logger.debug(f"[{self.role}] VST Unit Instance created (ID: {self.sys_id})")

    # ---------------------------------------------------------
    # コマンド制御フロー
    # ---------------------------------------------------------

    def control(self, payload):
        """
        [入口] 命令をパースし、個別ロジック(execute_logic)を叩く。
        """
        # 1. コマンドIDの紐付け (ref_cmd_id に保存)
        self.ref_cmd_id = payload.get("cmd_id", payload.get("ref_cmd_id", 0))

        # 2. 接頭語に基づいた属性の自動更新
        for key, value in payload.items():
            if any(key.startswith(pre) for pre in ["act_", "val_", "env_", "sys_", "log_"]):
                setattr(self, key, value)
        
        # 3. 具象クラスの個別ロジックを実行
        self.execute_logic(payload)

    def execute_logic(self, payload):
        """[継承先でオーバーライド]"""
        logger.warning(f"[{self.role}] execute_logic is not implemented.")
        pass

    # ---------------------------------------------------------
    # 応答・報告プロトコル (WES 2026)
    # ---------------------------------------------------------

    def send_response(self, cmd_status=None, log_msg=None, log_code=None):
        """
        Hubに対して /res トピックで応答を送り、DBのコマンドステータスを連動させる。
        """
        if log_msg: self.log_msg = log_msg
        if log_code: self.log_code = log_code

        # 1. DBの物理状態(node_status_current)を更新
        self.update_status()

        # 2. MQTTレスポンスペイロードの構築
        res_payload = {
            "vst_role_name": self.vst_role_name,
            "cmd_status": cmd_status,      # acknowledged / completed / failed
            "val_status": self.val_status, # 実際の物理状態
            "ref_cmd_id": self.ref_cmd_id,
            "log_msg": self.log_msg,
            "log_code": self.log_code,
            "log_ext": self.log_ext,
            "timestamp": time.time()
        }

        # Manager(NodeManager)経由でMQTT送信
        self.notify_manager("result", res_payload)
        
        # 3. DBのコマンド履歴(node_commands)を更新
        if self.ref_cmd_id and cmd_status:
            if cmd_status == "acknowledged":
                # 受領時刻(acked_at)を刻む
                self.db.mark_command_acknowledged(self.ref_cmd_id)
            else:
                # 完了/失敗。完了時刻(completed_at)を刻む
                self.finalize_command(status=cmd_status, msg=self.log_msg, code=self.log_code)

    def finalize_command(self, status="completed", msg=None, code=None, res=None):
        """
        コマンドを最終状態にし、時刻を記録する。
        """
        if self.ref_cmd_id:
            target_msg = msg if msg is not None else self.log_msg
            target_code = code if code is not None else self.log_code
            
            # DBの completed_at を更新
            self.db.finalize_command(self.ref_cmd_id, status, target_msg, target_code, res)
            logger.info(f"[{self.role}] Command {self.ref_cmd_id} finalized as {status}")
            
            # 完了・エラーは最終状態なので、アクティブなIDをクリア
            if status in ["completed", "failed", "error"]:
                self.ref_cmd_id = 0
        else:
            logger.debug(f"[{self.role}] No active command ID to finalize.")

    def send_event(self, event_name, extra_data=None):
        """ 状態変化やエラーを /event トピックへ通知 """
        event_payload = self.report()
        event_payload["event"] = event_name
        if extra_data: event_payload.update(extra_data)

        self.notify_manager("event_fired", event_payload)
        
        # DBにイベントログを記録
        self.db.insert_event_log(self.sys_id, self.vst_role_name, {
            "log_level": self.get_level_from_code(self.log_code),
            "log_msg": f"Event: {event_name} - {self.log_msg}",
            "log_code": self.log_code,
            "event_data": event_payload
        })

    def update_status(self, val_status=None, log_code=None, log_ext=None):
        """ 物理状態をDBへ同期する """
        if val_status is not None: self.val_status = val_status
        if log_code is not None: self.log_code = log_code
        if log_ext is not None: 
            if isinstance(log_ext, dict) and isinstance(self.log_ext, dict):
                self.log_ext.update(log_ext)
            else:
                self.log_ext = log_ext

        payload = {
            "val_status": self.val_status,
            "log_code": self.log_code,
            "log_ext": self.log_ext
        }
        
        try:
            self.db.update_node_status(self.sys_id, self.role, payload)
        except Exception as e:
            logger.error(f"[{self.role}] Failed to update DB status: {e}")

    # ---------------------------------------------------------
    # ユーティリティ
    # ---------------------------------------------------------

    def notify_manager(self, event_type, payload=None):
        """コールバック仲介"""
        if self.event_callback:
            self.event_callback(self.vst_role_name, event_type, payload)

    def report(self):
        """現在の全 prefixed 属性を抽出"""
        data = {"vst_role_name": self.vst_role_name, "ref_cmd_id": self.ref_cmd_id}
        for key, value in self.__dict__.items():
            if any(key.startswith(pre) for pre in ["val_", "env_", "sys_", "log_", "net_", "act_", "hw_"]):
                if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                    data[key] = value
        return data

    def get_level_from_code(self, code):
        """エラーコード(WES 2026)からログレベルを判定"""
        if code >= 500: return "error"
        if code >= 400: return "warning"
        return "info"

    def stop(self):
        """終了処理"""
        logger.info(f"[{self.role}] Stopping unit...")
        self.update_status(val_status="idle", log_code=200)