import time

class WildLinkVSTBase:
    """すべてのWildLink VSTユニットが継承すべき基本クラス"""
    
    def __init__(self, config):
        # 命名規則に基づいた基本プロパティ
        self.sys_id = config.get("sys_id", "unknown")
        self.val_name = config.get("val_name", "generic_unit")
        self.val_enabled = config.get("val_enabled", True)
        self.val_interval = config.get("val_interval", 10)
        
        self.val_status = "idle"
        self.log_msg = "Initialized"
        self.last_sense_time = 0

    def update(self, act_cmds=None):
        """マネージャーから毎秒呼ばれるメインループ"""
        if not self.val_enabled:
            self.val_status = "disabled"
            return self._report()

        # 1. 外部からのアクション命令(act_xxx)を処理
        if act_cmds:
            self.execute_actions(act_cmds)

        # 2. 定期的な計測(sense)が必要かチェック
        now = time.time()
        if now - self.last_sense_time >= self.val_interval:
            self.sense()
            self.last_sense_time = now

        return self._report()

    def sense(self):
        """[継承先で上書き] センサー計測やデータ収集のロジックを記述"""
        pass

    def execute_actions(self, cmds):
        """[継承先で上書き] act_xxx 系の命令（配信開始など）を記述"""
        for key, value in cmds.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def _report(self):
        """現在の全ステータス(env_, sys_, val_, log_)を抽出して辞書で返す"""
        report = {}
        for key, value in self.__dict__.items():
            if any(key.startswith(pre) for pre in ["env_", "sys_", "val_", "log_", "net_"]):
                # サブプロセスなどのオブジェクトは除外
                if not hasattr(value, '__dict__') or isinstance(value, (str, int, float, bool, list, dict)):
                    report[key] = value
        return report