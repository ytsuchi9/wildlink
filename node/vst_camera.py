import os
import subprocess
import socket
import time
import fcntl
import threading
from common.vst_base import WildLinkVSTBase

class VST_Camera(WildLinkVSTBase):
    def __init__(self, role, params, mqtt, event_callback=None, config=None):
        super().__init__(role, params, mqtt, event_callback)
        self.config = config or {}
        self.sys_id = self.config.get("sys_id") or os.getenv("SYS_ID", "node_001")

        self.hw_driver = str(self.config.get("hw_driver", "CSI_CAM")).upper()
        self.hw_device = self.config.get("hw_bus_addr") or "/dev/video0" 
        self.val_res = params.get("val_res", "320x240")
        self.val_fps = params.get("val_fps", 5)
        
        self.hub_ip = params.get("hub_ip", "192.168.1.102")
        default_port = 5005 if self.hw_driver == "CSI_CAM" else 5006
        self.dest_port = int(params.get("net_port") or default_port)
        
        from common.wmp_core import WMPHeader
        self.wmp = WMPHeader(node_id=self.sys_id, role=self.role, media_type=2)
        
        self.act_run = False 
        self.val_status = "idle"
        self.process = None
        self.thread = None
        self.stop_event = threading.Event()
        
        print(f"📷 [{self.role}] Initialized: Node={self.sys_id}, Driver={self.hw_driver}, Port={self.dest_port}")

    @property
    def status_dict(self):
        return {
            "vst_role_name": self.role,
            "val_status": self.val_status,
            "act_run": self.act_run,
            "log_msg": f"Streaming via {self.hw_driver} on {self.hw_device}" if self.act_run else "Ready"
        }

    def execute_logic(self, payload):
        target_run = payload.get("act_run")
        if target_run is None and "action" in payload:
            target_run = (payload["action"] == "start")

        if target_run is not None:
            if self.act_run != target_run:
                self.act_run = target_run
                if self.act_run:
                    self.start_streaming()
                else:
                    self.stop_streaming()
            return True # MainManagerに成功を返す
        return False

    def start_streaming(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._streaming_loop, name=f"Thread-{self.role}")
        self.thread.daemon = True
        self.thread.start()
        self.val_status = "streaming"
        # 💡 notify_manager がない場合は、Baseクラスの機能を使うか、ここでの呼び出しを消す
        # 今回はMainManagerが直後にDB更新するため、エラー防止のために削除または修正
        # self.notify_manager() # ←これがエラーの原因でした

    def stop_streaming(self):
        self.stop_event.set()
        if self.process:
            self.process.terminate()
            try: self.process.wait(timeout=1.0)
            except: self.process.kill()
            self.process = None
        self.val_status = "idle"
        print(f"⏹️ [{self.role}] Stream stopped.")

    def _streaming_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dest_addr = (self.hub_ip, self.dest_port)
        
        if "CSI" in self.hw_driver:
            w, h = self.val_res.split('x')
            cmd = ["rpicam-vid", "-t", "0", "--inline", "--nopreview",
                   "--width", w, "--height", h, "--framerate", str(self.val_fps),
                   "--codec", "mjpeg", "--flush", "-o", "-"]
        else:
            cmd = ["ffmpeg", "-y", "-f", "v4l2", "-input_format", "mjpeg",
                   "-video_size", self.val_res, "-framerate", str(self.val_fps),
                   "-i", self.hw_device, "-c:v", "copy", "-f", "mjpeg", "-an", "pipe:1"]

        try:
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            fd = self.process.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            buffer = b""
            while not self.stop_event.is_set():
                try:
                    chunk = self.process.stdout.read(65536)
                    if chunk: buffer += chunk
                    elif self.process.poll() is not None: break
                except (BlockingIOError, TypeError):
                    time.sleep(0.005)
                    continue

                while True:
                    start = buffer.find(b'\xff\xd8')
                    end = buffer.find(b'\xff\xd9', start)
                    if start != -1 and end != -1:
                        frame = buffer[start:end+2]
                        if self.act_run: self.wmp.send_large_data(sock, dest_addr, frame)
                        buffer = buffer[end+2:]
                    else: break
                if len(buffer) > 2000000: buffer = b""
        except Exception as e:
            self.val_status = "error"
        finally:
            if self.process: self.process.terminate()
            sock.close()

    def stop(self):
        self.stop_streaming()