import subprocess
import os
import sys
from vst_base import WildLinkVSTBase

class WildLinkUnit(WildLinkVSTBase):
    def __init__(self, config):
        super().__init__(config) # 親クラスの初期化
        
        # カメラ固有の設定
        self.hw_pin = config.get("hw_pin", "/dev/video0")
        self.val_res = config.get("val_res", "320x240")
        self.val_fps = config.get("val_fps", 5)
        
        # アクション状態
        self.act_stream = config.get("act_stream", False)
        self.process = None

    def execute_actions(self, cmds):
        """配信フラグの変更を監視"""
        super().execute_actions(cmds)
        
        # act_stream の状態が変わった時のプロセス管理
        if self.act_stream and not self.process:
            self._start_wmp_tx()
        elif not self.act_stream and self.process:
            self._stop_wmp_tx()

    def _start_wmp_tx(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        tx_script = os.path.join(script_dir, "wmp_stream_tx.py")
        
        self.process = subprocess.Popen(["python3", tx_script])
        self.val_status = "streaming"
        self.log_msg = "WMP Stream Started"

    def _stop_wmp_tx(self):
        if self.process:
            self.process.terminate()
            self.process = None
        self.val_status = "idle"
        self.log_msg = "WMP Stream Stopped"

    def sense(self):
        """（オプション）カメラの生存確認や温度取得など"""
        if self.process and self.process.poll() is not None:
            self.log_msg = "Error: TX Process died"
            self.process = None
            self.val_status = "error"