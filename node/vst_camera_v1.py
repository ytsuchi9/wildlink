# /opt/wildlink/node/vst_camera.py
import subprocess
import os
from vst_base import WildLinkVSTBase

class VSTCamera(WildLinkVSTBase):
    def __init__(self, config):
        super().__init__(config)
        # DB(config)から設定を取得。なければデフォルト値を使用
        self.hw_pin = config.get("hw_pin", "/dev/video0")
        self.val_res = config.get("val_res", "320x240")
        self.val_fps = config.get("val_fps", 5)
        
        self.act_stream = False
        self.process = None

    def update(self, cmd_dict=None):
        """
        cmd_dict に {"act_stream": True} などが含まれている場合に
        ストリーミングを開始/停止する
        """
        if cmd_dict and "act_stream" in cmd_dict:
            target_state = cmd_dict["act_stream"]
            if target_state and not self.process:
                self._start_stream()
            elif not target_state and self.process:
                self._stop_stream()

        # プロセスの生存確認
        if self.process and self.process.poll() is not None:
            self.log_msg = "Error: Stream process died"
            self.process = None
            self.act_stream = False

        return {
            "act_stream": self.act_stream,
            "val_status": "streaming" if self.act_stream else "idle",
            "log_msg": self.log_msg
        }

    def _start_stream(self):
        script_path = os.path.join(os.path.dirname(__file__), "wmp_stream_tx.py")
        # 外部の送信スクリプトを叩く（設定を引数で渡せるように拡張可能）
        self.process = subprocess.Popen(["python3", script_path])
        self.act_stream = True
        self.log_msg = "Stream Started"

    def _stop_stream(self):
        if self.process:
            self.process.terminate()
            self.process = None
        self.act_stream = False
        self.log_msg = "Stream Stopped"