import subprocess
import os

class WildLinkUnit:
    def __init__(self, config):
        self.val_name = config.get("val_name", "camera")
        self.hw_pin = config.get("hw_pin", "/dev/video0")
        self.val_res = config.get("val_res", "640x480")
        self.val_fps = config.get("val_fps", 10)
        self.act_strobe = config.get("act_strobe", False)
        
        self.log_msg = "Idle"
        self.process = None
        self.out_file = "/dev/shm/latest.jpg" # 高速化のため共有メモリを使用

    def start_ffmpeg(self):
        if self.process: return
        
        # FFmpegコマンド (MJPEGストリームから静止画を連続上書き)
        cmd = (
            f"ffmpeg -y -i {self.hw_pin} -f image2 -vf fps={self.val_fps} "
            f"-s {self.val_res} -update 1 {self.out_file} > /dev/null 2>&1"
        )
        self.process = subprocess.Popen(cmd, shell=True)
        self.log_msg = "Running"

    def stop_ffmpeg(self):
        if self.process:
            self.process.terminate()
            self.process = None
            # 前の画像を消去
            if os.path.exists(self.out_file):
                os.remove(self.out_file)
        self.log_msg = "Idle"

    def update(self):
        if self.act_strobe:
            if not self.process:
                self.start_ffmpeg()
            return {"cam_status": "streaming"}
        else:
            if self.process:
                self.stop_ffmpeg()
            return {"cam_status": "stopped"}