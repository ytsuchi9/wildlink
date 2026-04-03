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
    
    [主な役割]
    1. 命名規則に基づく属性(val_, act_等)の自動同期
    2. コマンド実行状態(cmd_status)と物理状態(val_status)の分離管理
    3. Hub(MQTT)およびDBへの標準化された応答処理
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
        self.log_ext = {}              # 詳細コンテキスト (旧 val_params を JSON辞書として保持)
        self.log_msg = "Initialized"
        
        self.val_enabled = self.params.get("val_enabled", True)
        self.ref_cmd_id = 0            # 処理中のコマンドID
        
        # 起動時のパラメータ展開 (log_ext への変換を含む)
        if isinstance(self.params, dict):
            # DBの log_ext (JSON) を復元
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
        [入口] 命令をパースし、属性を自動更新してから個別ロジック(execute_logic)を叩く。
        """
        # 1. コマンドIDの紐付け
        self.ref_cmd_id = payload.get("cmd_id", payload.get("ref_cmd_id", 0))

        # 2. 接頭語(val_, act_等)に基づいた属性の自動更新 (WES 2026 自動マッピング)
        for key, value in payload.items():
            if any(key.startswith(pre) for pre in ["act_", "val_", "env_", "sys_", "log_"]):
                setattr(self, key, value)
        
        # 3. 具象クラス（カメラ等）の個別ロジックを実行
        self.execute_logic(payload)

    def execute_logic(self, payload):
        """[継承先でオーバーライド] 具体的なハードウェア操作を記述"""
        logger.warning(f"[{self.role}] execute_logic is not implemented.")
        pass

    # ---------------------------------------------------------
    # 応答・報告プロトコル (WES 2026)
    # ---------------------------------------------------------

    def send_response(self, cmd_status=None, log_msg=None, log_code=None):
        """
        Hub に対して /res トピックで応答を送り、DBのステータスも連動させる。
        """
        if log_msg: self.log_msg = log_msg
        if log_code: self.log_code = log_code

        # 1. DBのステータスを現在の状態で同期
        self.update_status()

        # 2. レスポンスペイロードの構築
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
        
        if cmd_status and self.ref_cmd_id:
            self.finalize_command(status=cmd_status, msg=self.log_msg, code=self.log_code)

    def finalize_command(self, status="completed", msg=None, code=None, res=None):
        """
        DBBridge を使用して DB 上のコマンドレコードを最終更新する。
        """
        if self.ref_cmd_id:
            target_msg = msg if msg is not None else self.log_msg
            target_code = code if code is not None else self.log_code
            
            # DBの completed_at 等を更新
            self.db.finalize_command(self.ref_cmd_id, status, target_msg, target_code, res)
            logger.info(f"[{self.role}] Command {self.ref_cmd_id} finalized as {status}")
            
            # 完了後、コマンドIDをクリア（二重送信防止）
            if status in ["completed", "failed"]:
                self.ref_cmd_id = 0
        else:
            logger.debug(f"[{self.role}] No active command ID to finalize.")

    def send_event(self, event_name, extra_data=None):
        """
        状態変化やエラーを /event トピックへ通知し、DBにイベントログを記録する。
        """
        event_payload = self.report()
        event_payload["event"] = event_name
        if extra_data: event_payload.update(extra_data)

        # 1. Manager を通じて通知 (MQTT: .../event)
        self.notify_manager("event_fired", event_payload)
        
        # 2. DB にイベントログを記録
        self.db.insert_event_log(self.sys_id, self.vst_role_name, {
            "log_level": self.get_level_from_code(self.log_code),
            "log_msg": f"Event: {event_name} - {self.log_msg}",
            "log_code": self.log_code,
            "event_data": event_payload
        })

    def send_data(self, data_dict):
        """
        センサー値などの継続的なデータを /env トピックへ送信する。
        """
        payload = {
            "val_time": datetime.now().isoformat(),
            "vst_role_name": self.vst_role_name
        }
        payload.update(data_dict)
        self.notify_manager("data_pushed", payload)

    def update_status(self, val_status=None, log_code=None, log_ext=None):
        """
        [WES 2026 準拠] DBの node_status_current を更新する。
        引数が指定された場合は内部変数を更新してからDBへ書き込む。
        """
        if val_status is not None: self.val_status = val_status
        if log_code is not None: self.log_code = log_code
        if log_ext is not None: 
            # 辞書ならマージ、それ以外なら上書き
            if isinstance(log_ext, dict) and isinstance(self.log_ext, dict):
                self.log_ext.update(log_ext)
            else:
                self.log_ext = log_ext

        # DBへ書き込むペイロードの構築
        # DBBridge.update_node_status が log_code, log_ext を扱える前提
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
        """MainManager へのコールバックを仲介"""
        if self.event_callback:
            self.event_callback(self.vst_role_name, event_type, payload)

    def report(self):
        """現在の全 prefixed 属性を辞書形式で抽出"""
        data = {"vst_role_name": self.vst_role_name, "ref_cmd_id": self.ref_cmd_id}
        for key, value in self.__dict__.items():
            # log_code や log_ext も log_ プレフィックスにより自動的に収集される
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
        """
        [重要] ユニット停止時のクリーンアップ。
        継承先では、必ずプロセス終了ロジック(条項15)を実装すること。
        [WES 2026] 停止時は idle 状態をDBへ報告してから終了
        """
        logger.info(f"[{self.role}] Stopping unit...")
        self.update_status(val_status="idle", log_code=200)