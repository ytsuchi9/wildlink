import sys
import os
import subprocess
import socket
import time
import fcntl
import threading
from common.vst_base import WildLinkVSTBase

class VST_Camera(WildLinkVSTBase):
    def __init__(self, role, params, mqtt, event_callback=None):
        super().__init__(role, params, mqtt, event_callback)
        
        # ロールに基づくハードウェア抽象化
        self.hw_type = "pi" if self.role == "cam_main" else "usb"
        self.hw_device = None if self.hw_type == "pi" else "/dev/video0"

        self.val_res = params.get("val_res", "320x240")
        self.val_fps = params.get("val_fps", 5)
        
        from common.wmp_core import WMPHeader
        self.wmp = WMPHeader(node_id="node_001", media_type=2)
        
        self.act_run = False 
        self.val_status = "idle"
        self.process = None
        self.stop_event = threading.Event()
        
        self.start_camera_process()

    @property
    def status_dict(self):
        """Managerのレポート機能が参照する現在のステータス"""
        return {
            "val_status": self.val_status,
            "act_stream": self.act_run,
            "log_msg": f"Streaming via {self.hw_type}" if self.act_run else "Ready"
        }

    def start_camera_process(self):
        print(f"🎬 [{self.role}] Pre-starting camera process...")
        self.thread = threading.Thread(target=self._streaming_loop)
        self.thread.daemon = True
        self.thread.start()

    def execute_logic(self, payload):
        """コマンドによる制御"""
        action = payload.get("action")
        # act_run (Boolean) または action (start/stop) の両方に対応
        if "act_run" in payload:
            self.act_run = payload["act_run"]
        elif action == "start":
            self.act_run = True
        elif action == "stop":
            self.act_run = False
            
        self.val_status = "streaming" if self.act_run else "idle"

    def stop(self):
        self.stop_event.set() 
        if self.process:
            self.process.terminate()
            try: self.process.wait(timeout=1)
            except: self.process.kill()
        print(f"✅ [{self.role}] Unit stopped.")

    def _streaming_loop(self):
        time.sleep(0.5)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 宛先IP/Port (Pi=5005, USB=5006)
        dest_addr = ("192.168.1.102", 5005 if self.hw_type == "pi" else 5006)
        
        if self.hw_type == "pi":
            w, h = self.val_res.split('x')
            cmd = ["rpicam-vid", "-t", "0", "--inline", "--nopreview",
                   "--width", w, "--height", h, "--framerate", str(self.val_fps),
                   "--codec", "mjpeg", "--flush", "-o", "-"]
        else:
            cmd = ["ffmpeg", "-y", "-f", "v4l2", "-input_format", "mjpeg",
                   "-video_size", self.val_res, "-framerate", str(self.val_fps),
                   "-i", self.hw_device, "-c:v", "copy", "-f", "mjpeg", "-an", "pipe:1"]

        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        
        # 非ブロッキング読み取り設定
        fd = self.process.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        buffer = b""
        while not self.stop_event.is_set():
            try:
                chunk = self.process.stdout.read(16384)
                if chunk: buffer += chunk
            except: pass

            a = buffer.rfind(b'\xff\xd8')
            b = buffer.find(b'\xff\xd9', a)
            
            if a != -1 and b != -1:
                frame = buffer[a:b+2]
                if self.act_run: # ゲートが開いているときのみ送信
                    self.wmp.send_large_data(sock, dest_addr, frame, flags=1)
                buffer = buffer[b+2:]
                time.sleep(0.01)
            else:
                time.sleep(0.001)

        sock.close()