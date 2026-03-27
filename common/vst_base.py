import time
import json

class WildLinkVSTBase:
    """
    WildLink Event Standard (WES) 2026 準拠
    すべての WildLink VST (Virtual System Unit) の基底クラス。
    命名規則の適用、MQTTトピックへの自動振り分け、コマンド応答ロジックを統括する。
    """
    
    def __init__(self, sys_id, role, params, mqtt_client=None, event_callback=None):
        self.sys_id = sys_id   # ノードの識別子 (node_001等)
        self.role = role       # 役割名 (cam_main, log_sys等)
        self.params = params   # DBの val_params (dict)
        self.mqtt = mqtt_client
        self.event_callback = event_callback
        
        # --- WES 2026 標準ステータス変数の初期化 ---
        self.val_status = "idle"
        self.val_enabled = params.get("val_enabled", True)
        self.log_msg = "Initialized"
        self.log_code = 200
        self.ref_cmd_id = 0    # 現在処理中、または直近に処理したコマンドID
        
        self.last_sense_time = 0

    def control(self, payload):
        """
        外部（MQTT）からの命令をパースし、属性を更新してからロジックを実行する。
        """
        # 1. コマンドIDの抽出 (WES 2026: 応答紐付け用)
        if "cmd_id" in payload:
            self.ref_cmd_id = payload["cmd_id"]

        # 2. 接頭語に基づいた属性の自動更新
        for key, value in payload.items():
            if any(key.startswith(pre) for pre in ["act_", "val_", "env_", "sys_"]):
                setattr(self, key, value)
        
        # 3. 具象クラス（カメラ等）の個別ロジックを実行
        self.execute_logic(payload)

    def execute_logic(self, payload):
        """[継承先でオーバーライド] 具体的なハードウェア操作や処理を記述"""
        pass

    def send_event(self, event_name, extra_data=None):
        """
        WES 2026: 状態変化やコマンド完了を '.../event' トピックへ通知する。
        """
        if not self.mqtt:
            return

        # 基本情報の構築
        event_payload = {
            "role": self.role,
            "event": event_name,
            "val_status": self.val_status,
            "log_msg": self.log_msg,
            "log_code": self.log_code,
            "ref_cmd_id": self.ref_cmd_id, # どのコマンドへの応答かを明示
            "timestamp": time.time()
        }

        # 追加データがあればマージ
        if extra_data and isinstance(extra_data, dict):
            event_payload.update(extra_data)

        # MQTT送信 (nodes/{sys_id}/{role}/event)
        self.mqtt.publish_event(self.sys_id, self.role, event_payload)
        
        # マネージャー（DB更新担当）にも通知
        self.notify_manager("event_fired")

    def send_data(self, data_dict):
        """
        WES 2026: センサー値やログ本文などの生データを '.../env' トピックへ送信する。
        """
        if not self.mqtt:
            return

        # 常に最新の基本ステータスを混ぜる
        payload = {
            "val_time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        }
        payload.update(data_dict)

        # MQTT送信 (nodes/{sys_id}/{role}/env)
        self.mqtt.publish_env(self.sys_id, self.role, payload)

    def notify_manager(self, event_type="status_changed"):
        """
        MainManagerに内部通知を送り、必要に応じてDB更新などをトリガーさせる。
        """
        if self.event_callback:
            self.event_callback(self.role, event_type)

    def poll(self):
        """MainManagerから周期的に呼ばれる。自律動作（ポーリング等）が必要な場合に使用。"""
        if not self.val_enabled:
            return
        pass

    def report(self):
        """
        現在のオブジェクト内にある全パラメータを辞書形式で抽出する。
        主にHub経由で node_status（最新状態テーブル）を更新するために使用。
        """
        data = {}
        # role と ref_cmd_id は必須
        data["role"] = self.role
        data["ref_cmd_id"] = self.ref_cmd_id
        
        # 接頭語ルールに該当する属性のみを抽出
        for key, value in self.__dict__.items():
            if any(key.startswith(pre) for pre in ["env_", "sys_", "val_", "log_", "net_", "act_"]):
                # シリアライズ可能な型のみを対象とする
                if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                    data[key] = value
        return data