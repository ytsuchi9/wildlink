import sys
import os
import subprocess
import socket
import time
import fcntl
import threading

class VST_Camera:
    def __init__(self, role, params, mqtt):
        self.role = role
        self.params = params
        self.mqtt = mqtt
        
        # デバイス設定
        if self.role == "cam_main":
            self.hw_type = "pi"
            self.hw_device = None
        else:
            self.hw_type = "usb"
            self.hw_device = "/dev/video0"

        self.val_res = params.get("val_res", "320x240")
        self.val_fps = params.get("val_fps", 5)
        self.val_status = "idle"
        
        from common.wmp_core import WMPHeader
        self.wmp = WMPHeader(node_id="node_001", media_type=2)
        
        self.gate_open = False  # 映像を流すかどうかの門
        self.process = None
        self.stop_event = threading.Event()
        
        # 起動時にプロセスを立ち上げてしまう
        self.start_camera_process()

    def start_camera_process(self):
        """カメラプロセスを裏で回し始める"""
        print(f"🎬 [{self.role}] Pre-starting camera process...")
        self.thread = threading.Thread(target=self._streaming_loop)
        self.thread.daemon = True
        self.thread.start()

    def control(self, payload):
        """配信のON/OFF（門の開閉）だけを制御"""
        if "act_run" in payload:
            self.gate_open = payload["act_run"]
            self.val_status = "streaming" if self.gate_open else "idle"
            status_label = "OPEN" if self.gate_open else "CLOSED"
            print(f"📽️ [{self.role}] Stream Gate: {status_label}")

    def _streaming_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 本来はpayloadで受け取るが、常時起動のためデフォルトのHubを指定
        dest_addr = ("192.168.1.102", 5005 if self.hw_type == "pi" else 5006)
        
        # コマンド生成（初期化ラグを減らすため露出固定などを追加）
        if self.hw_type == "pi":
            width, height = self.val_res.split('x')
            cmd = [
                "rpicam-vid", "-t", "0", "--inline", "--nopreview",
                "--width", width, "--height", height,
                "--framerate", str(self.val_fps),
                "--codec", "mjpeg", "--flush", "--denoise", "cdn_off",
                "--shutter", "20000", "--awbgains", "1.5,1.5", 
                "-o", "-"
            ]
        else:
            cmd = [
                "ffmpeg", "-y", 
                "-f", "v4l2", 
                "-input_format", "mjpeg", # ★ カメラがMJPEG対応なら直接受ける
                "-video_size", self.val_res,
                "-framerate", str(self.val_fps),
                "-i", self.hw_device,
                "-c:v", "copy",           # ★ 再エンコードせずそのまま流す（CPU負荷激減）
                "-f", "mjpeg", 
                "-an",                    # 音声なし
                "pipe:1"
            ]

        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # ノンブロッキング設定
        for p in [self.process.stdout, self.process.stderr]:
            fd = p.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        buffer = b""

        while not self.stop_event.is_set():
            # 映像データ読み込み（常にバッファを空にするために読み続ける）
            try:
                while True:
                    chunk = self.process.stdout.read(16384)
                    if not chunk: break
                    buffer += chunk
            except: pass

            # MJPEGフレーム切り出し
            a = buffer.rfind(b'\xff\xd8')
            b = buffer.find(b'\xff\xd9', a)
            
            if a != -1 and b != -1:
                frame = buffer[a:b+2]
                
                # ★ ここが重要：門が開いている時だけ送信する
                if self.gate_open:
                    self.wmp.send_large_data(sock, dest_addr, frame, flags=1)
                
                buffer = buffer[b+2:]
                time.sleep(1.0 / self.val_fps * 0.5) 
            else:
                time.sleep(0.001)

        if self.process:
            self.process.terminate()
        sock.close()