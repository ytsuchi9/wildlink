import subprocess
import os
import signal
from common.vst_base import WildLinkVSTBase

class VST_Camera(WildLinkVSTBase):
    def __init__(self, role, params, mqtt_client, event_callback):
        super().__init__(role, params, mqtt_client, event_callback)
        self.process = None
        # DBの設定(val_params)から解像度などを取得
        self.val_res = params.get("val_res", "640x480")
        self.val_fps = params.get("val_fps", 15)
        
    def execute_logic(self, payload):
        """MainManagerからのcontrol命令(action)をここで実行"""
        action = payload.get("action")
        
        if action == "start":
            self.start_stream()
        elif action == "stop":
            self.stop_stream()

    def start_stream(self):
        if self.process and self.process.poll() is None:
            self.log_msg = "Already streaming"
            return

        # 実際の配信コマンド (例: libcamera + ffmpeg/mediamtx)
        # ここでは role (cam_main等) に応じて配信パスを変える設計
        stream_url = f"rtsp://localhost:8554/{self.role}"
        
        cmd = f"libcamera-vid -t 0 --inline --width 640 --height 480 --framerate {self.val_fps} -o - | ffmpeg -i - -c copy -f rtsp {stream_url}"
        
        try:
            self.process = subprocess.Popen(cmd, shell=True, preexec_fn=os.setsid)
            self.val_status = "streaming"
            self.log_msg = f"Started streaming to {stream_url}"
            self.log_code = 200
            print(f"📹 [{self.role}] Stream started.")
        except Exception as e:
            self.val_status = "error"
            self.log_msg = str(e)
            self.log_code = 500

    def stop_stream(self):
        if self.process:
            # プロセスグループ全体を終了させる
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            self.process = None
            self.val_status = "idle"
            self.log_msg = "Stream stopped"
            self.log_code = 200
            print(f"🛑 [{self.role}] Stream stopped.")

    def poll(self):
        """定期的にプロセスが生きているか監視"""
        if self.val_status == "streaming":
            if self.process and self.process.poll() is not None:
                self.val_status = "error"
                self.log_msg = "Process died unexpectedly"
                self.log_code = 503