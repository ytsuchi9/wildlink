import logging
from .vst_base import VstBase

class VstSystem(VstBase):
    """
    システム管理ユニット (Role: system, node)
    ログ収集モードの管理や、本体のヘルスチェックを担当
    """
    def __init__(self, sys_id, role, config):
        super().__init__(sys_id, role, config)
        self.log_mode = config.get('val_params', {}).get('log_mode', 'mqtt')
        logging.info(f"[{self.role}] Initialized with log_mode: {self.log_mode}")

    def on_command(self, cmd_type, params):
        if cmd_type == 'set_log_mode':
            new_mode = params.get('mode')
            if new_mode in ['mqtt', 'poll']:
                self.log_mode = new_mode
                self.update_status('active', f"Log mode changed to {new_mode}")
                return True
        return False

    def get_vitals(self):
        # システム固有のバイタル情報を返すロジック
        return {
            "log_mode": self.log_mode
        }