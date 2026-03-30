import json
import time
from common.db_bridge import DBBridge
from common.logger_config import get_logger

logger = get_logger("vst_base")

class WildLinkVSTBase:
    """
    WildLink Event Standard (WES) 2026 準拠
    すべての WildLink VST (Virtual System Unit) の基底クラス。
    
    [特徴]
    - 命名規則 (val_, env_, sys_, act_) に基づく属性の自動更新
    - MQTT トピックへの自動振り分け (event, env, status)
    - DBBridge を介したイベントログとコマンド完了通知の統合
    - 既存の send_event / send_data メソッドとの完全な互換性
    """
    
    def __init__(self, sys_id, role, params, mqtt_client=None, event_callback=None):
        self.sys_id = sys_id   # ノードの識別子 (node_001等)
        self.role = role       # 役割名 (cam_main, log_sys等)
        self.role_name = role  # 旧コードとの互換性用
        self.params = params   # DBの val_params (dict)
        self.mqtt = mqtt_client
        self.event_callback = event_callback
        
        # 共通の DBBridge インスタンスを保持
        self.db = DBBridge()
        
        # --- WES 2026 標準ステータス変数の初期化 ---
        self.val_status = "idle"
        self.val_enabled = params.get("val_enabled", True)
        self.log_msg = "Initialized"
        self.log_code = 200
        self.ref_cmd_id = 0     # 現在処理中、または直近に処理したコマンドID
        
        self.last_sense_time = 0
        self.is_active = params.get("is_active", 1)

    def control(self, payload):
        """
        外部（MQTT）からの命令をパースし、属性を自動更新してから個別ロジックを実行する。
        """
        # 1. コマンドIDの抽出 (WES 2026: 応答紐付け用)
        if "cmd_id" in payload:
            self.ref_cmd_id = payload["cmd_id"]
        elif "ref_cmd_id" in payload:
            self.ref_cmd_id = payload["ref_cmd_id"]

        # 2. 接頭語に基づいた属性の自動更新
        for key, value in payload.items():
            if any(key.startswith(pre) for pre in ["act_", "val_", "env_", "sys_", "log_"]):
                setattr(self, key, value)
        
        # 3. 具象クラス（カメラ等）の個別ロジックを実行
        # execute_logic が未定義の場合は control_logic (旧) を探すか、何もしない
        if hasattr(self, 'execute_logic'):
            self.execute_logic(payload)
        elif hasattr(self, 'control_logic'):
            self.control_logic(payload)

    def execute_logic(self, payload):
        """[継承先でオーバーライド] 具体的なハードウェア操作や処理を記述"""
        pass

    def send_event(self, event_name, extra_data=None):
        """
        WES 2026: 状態変化やコマンド完了を '.../event' トピックへ通知し、DBに記録する。
        """
        # 基本情報の構築
        event_payload = {
            "role": self.role,
            "event": event_name,
            "val_status": self.val_status,
            "log_msg": self.log_msg,
            "log_code": self.log_code,
            "ref_cmd_id": self.ref_cmd_id,
            "timestamp": time.time()
        }

        # 追加データがあればマージ
        if extra_data and isinstance(extra_data, dict):
            event_payload.update(extra_data)

        # 1. MQTT送信 (nodes/{sys_id}/{role}/event)
        if self.mqtt:
            # publish_event メソッドがない場合は標準的な publish にフォールバック
            if hasattr(self.mqtt, 'publish_event'):
                self.mqtt.publish_event(self.sys_id, self.role, event_payload)
            else:
                topic = f"nodes/{self.sys_id}/{self.role}/event"
                self.mqtt.publish(topic, json.dumps(event_payload, ensure_ascii=False))
        
        # 2. DB にイベントログを記録
        self.db.insert_event_log(self.sys_id, self.role, {
            "log_level": self.get_level_from_code(self.log_code),
            "log_msg": f"Event: {event_name} - {self.log_msg}",
            "log_code": self.log_code,
            "event_data": event_payload
        })
        
        # 3. マネージャー（連動エンジン等）に通知
        self.notify_manager("event_fired")

    def send_data(self, data_dict):
        """
        WES 2026: センサー値や生データを '.../env' トピックへ送信する。
        """
        payload = {
            "val_time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "role": self.role
        }
        payload.update(data_dict)

        # MQTT送信
        if self.mqtt:
            if hasattr(self.mqtt, 'publish_env'):
                self.mqtt.publish_env(self.sys_id, self.role, payload)
            else:
                topic = f"nodes/{self.sys_id}/{self.role}/env"
                self.mqtt.publish(topic, json.dumps(payload, ensure_ascii=False))

    def update_status(self, payload=None):
        """
        DBの node_status_current を更新し、MQTTで最新状態を発信する。
        """
        if payload is None:
            payload = self.report()
        
        # DB更新
        self.db.update_node_status(self.sys_id, self.role, payload)
        
        # MQTT送信 (.../status)
        if self.mqtt:
            topic = f"nodes/{self.sys_id}/{self.role}/status"
            self.mqtt.publish(topic, json.dumps(payload, ensure_ascii=False))

    def finalize_command(self, status="completed", msg=None, code=None, res=None):
        """
        現在処理中のコマンド(ref_cmd_id)を完了状態にする。
        """
        if self.ref_cmd_id:
            target_msg = msg if msg is not None else self.log_msg
            target_code = code if code is not None else self.log_code
            self.db.finalize_command(self.ref_cmd_id, status, target_msg, target_code, res)
            logger.info(f"[{self.role}] Command {self.ref_cmd_id} finalized as {status}")
            self.ref_cmd_id = 0 # 完了後はクリア
        else:
            logger.debug(f"[{self.role}] No active command ID to finalize.")

    def notify_manager(self, event_type="status_changed"):
        """
        MainManagerに内部通知を送り、連動アクションをトリガーさせる。
        """
        if self.event_callback:
            # 引数形式の互換性 (role, event_type) 
            self.event_callback(self.role, event_type)

    def poll(self):
        """周期実行処理用スロット"""
        pass

    def report(self):
        """
        現在のオブジェクト内にある全パラメータを辞書形式で抽出する。
        """
        data = {"role": self.role, "ref_cmd_id": self.ref_cmd_id}
        for key, value in self.__dict__.items():
            if any(key.startswith(pre) for pre in ["env_", "sys_", "val_", "log_", "net_", "act_"]):
                if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                    data[key] = value
        return data

    def get_level_from_code(self, code):
        """エラーコードからログレベルを判定"""
        if code >= 500: return "error"
        if code >= 400: return "warning"
        return "info"

    def stop(self):
        """終了時のクリーンアップ"""
        logger.info(f"[{self.role}] Stopping unit.")