import time

class WildLinkVSTBase:
    """すべてのWildLink VSTユニットの基底クラス"""
    
    def __init__(self, role, params, mqtt_client=None, event_callback=None):
        self.role = role
        self.params = params  # DBの val_params
        self.mqtt = mqtt_client
        self.event_callback = event_callback
        
        # 命名規則に基づいた基本ステータス
        self.val_status = "idle"
        self.val_enabled = params.get("val_enabled", True)
        self.log_msg = "Initialized"
        self.log_code = 200
        self.last_sense_time = 0

    def control(self, payload):
        """外部（MQTTや他ユニット）からの命令を処理"""
        # act_ で始まる命令を自分自身のプロパティに書き込む
        for key, value in payload.items():
            if key.startswith("act_") or key.startswith("val_"):
                setattr(self, key, value)
        
        # 継承先で具体的なアクション（ストリーム開始など）を実装
        self.execute_logic(payload)

    def execute_logic(self, payload):
        """[継承先でオーバーライド] 具体的なハードウェア操作"""
        pass

    def poll(self):
        """MainManagerから 0.1s おきに呼ばれる"""
        if not self.val_enabled:
            return
        
        # 必要ならここで定期的な処理を行う
        pass

    def report(self):
        """現在の全情報を辞書で返す (Hubに送る用)"""
        data = {}
        for key, value in self.__dict__.items():
            if any(key.startswith(pre) for pre in ["env_", "sys_", "val_", "log_", "net_", "act_"]):
                # シリアライズ可能なデータのみ抽出
                if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                    data[key] = value
        return data