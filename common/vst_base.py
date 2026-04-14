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
    """

    def __init__(self, sys_id, role, params=None, mqtt_client=None, event_callback=None):
        """初期化：ベース属性のセット、WESステータス変数の準備、初期パラメータの展開を行います。"""
        self.sys_id = sys_id
        self.vst_role_name = role 
        self.role = role 
        self.params = params or {}
        self.mqtt = mqtt_client
        self.event_callback = event_callback
        
        self.db = DBBridge()
        
        # --- WES 2026 標準ステータス変数の初期化 ---
        self.val_status = "idle"       
        self.log_code = 200            
        self.log_ext = {}              
        self.log_msg = "Initialized"
        
        self.val_enabled = self.params.get("val_enabled", True)
        self.ref_cmd_id = 0            
        
        if isinstance(self.params, dict):
            self.log_ext = self.params.get("log_ext", {})
            for key, value in self.params.items():
                if any(key.startswith(pre) for pre in ["val_", "hw_", "net_"]):
                    setattr(self, key, value)

        logger.debug(f"[{self.role}] VST Unit Instance created (ID: {self.sys_id})")

    def control(self, payload):
        """
        [入口] HubからのコマンドJSONを受け取り、自身の属性（val_等）を更新した後、
        具象クラス固有の execute_logic へ処理を委譲します。
        """
        self.ref_cmd_id = payload.get("cmd_id", payload.get("ref_cmd_id", 0))

        for key, value in payload.items():
            if any(key.startswith(pre) for pre in ["act_", "val_", "env_", "sys_", "log_"]):
                setattr(self, key, value)
        
        self.execute_logic(payload)

    def execute_logic(self, payload):
        """[継承先で実装] コマンド受信時に実行される、カメラやセンサー特有の固有ロジックです。"""
        logger.warning(f"[{self.role}] execute_logic is not implemented.")
        pass

    def send_response(self, cmd_status=None, log_msg=None, log_code=None):
        """
        Hubに対して /res トピックで処理結果や受領確認を送り、DBのステータスと連動させます。
        """
        if log_msg: self.log_msg = log_msg
        if log_code: self.log_code = log_code

        self.update_status()

        res_payload = {
            "vst_role_name": self.vst_role_name,
            "cmd_status": cmd_status,      
            "val_status": self.val_status, 
            "ref_cmd_id": self.ref_cmd_id,
            "log_msg": self.log_msg,
            "log_code": self.log_code,
            "log_ext": self.log_ext,
            "timestamp": time.time()
        }

        self.notify_manager("result", res_payload)
        
        if self.ref_cmd_id and cmd_status:
            if cmd_status == "acknowledged":
                self.db.mark_command_acknowledged(self.ref_cmd_id)
            else:
                self.finalize_command(status=cmd_status, msg=self.log_msg, code=self.log_code)

    def finalize_command(self, status="completed", msg=None, code=None, res=None):
        """処理中のコマンドID (ref_cmd_id) を最終状態(完了・失敗など)にし、アクティブIDをクリアします。"""
        if self.ref_cmd_id:
            target_msg = msg if msg is not None else self.log_msg
            target_code = code if code is not None else self.log_code
            
            self.db.finalize_command(self.ref_cmd_id, status, target_msg, target_code, res)
            logger.info(f"[{self.role}] Command {self.ref_cmd_id} finalized as {status}")
            
            if status in ["completed", "failed", "error"]:
                self.ref_cmd_id = 0
        else:
            logger.debug(f"[{self.role}] No active command ID to finalize.")

    def send_event(self, event_name, extra_data=None):
        """状態変化やエラーなどの自発的なイベントを /event トピックへ通知し、ログを保存します。"""
        event_payload = self.report()
        event_payload["event"] = event_name
        if extra_data: event_payload.update(extra_data)

        self.notify_manager("event_fired", event_payload)
        
        self.db.insert_event_log(self.sys_id, self.vst_role_name, {
            "log_level": self.get_level_from_code(self.log_code),
            "log_msg": f"Event: {event_name} - {self.log_msg}",
            "log_code": self.log_code,
            "event_data": event_payload
        })

    def update_status(self, val_status=None, log_code=None, log_ext=None):
        """自身の現在の物理状態（val_status や log_ext）をDBの node_status_current へ直接同期します。"""
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

    def notify_manager(self, event_type, payload=None):
        """親クラス(MainManager等)のコールバック関数を呼び出し、内部イベントを中継します。"""
        if self.event_callback:
            self.event_callback(self.vst_role_name, event_type, payload)

    def report(self):
        """プレフィックス（val_, env_ 等）を持つすべての属性を収集し、現在の状態スナップショットとして返します。"""
        data = {"vst_role_name": self.vst_role_name, "ref_cmd_id": self.ref_cmd_id}
        for key, value in self.__dict__.items():
            if any(key.startswith(pre) for pre in ["val_", "env_", "sys_", "log_", "net_", "act_", "hw_"]):
                if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                    data[key] = value
        return data

    def get_level_from_code(self, code):
        """WESのハイブリッドエラーコード(数値)から、一般的なログレベル(info, warning, error)を判定します。"""
        if code >= 500: return "error"
        if code >= 400: return "warning"
        return "info"

    def stop(self):
        """システム終了時やユニット破棄時に呼ばれる安全な終了処理です。状態をidleに戻します。"""
        logger.info(f"[{self.role}] Stopping unit...")
        self.update_status(val_status="idle", log_code=200)