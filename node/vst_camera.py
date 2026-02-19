import sys
import os
import subprocess
import socket
import time
import fcntl
import threading

# --- パス解決 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
wildlink_root = os.path.dirname(current_dir)
common_path = os.path.join(wildlink_root, "common")
if common_path not in sys.path:
    sys.path.append(common_path)

from wmp_core import WMPHeader

class VSTCamera:
    def __init__(self, cam_type="pi", node_id="node_001"):
        self.hw_type = cam_type
        self.hw_device = "/dev/video0" if cam_type == "usb" else None
        self.node_id = node_id
        
        self.val_status = "idle"
        self.val_res = "320x240"
        self.val_fps = 5
        self.log_msg = ""
        self.log_code = ""
        
        self.process = None
        self.stop_event = threading.Event()
        self.thread = None
        self.wmp = WMPHeader(node_id=self.node_id, media_type=2)

    def control(self, payload):
            """MainManagerから呼ばれる制御窓口"""
            # ターゲットチェックを外すか、ログを出して確認するように変更
            # print(f"DEBUG: {self.hw_type} received command for {payload.get('hw_target')}")

            if "val_res" in payload: self.val_res = payload["val_res"]
            if "val_fps" in payload: self.val_fps = payload["val_fps"]
            
            if "act_run" in payload:
                if payload["act_run"]:
                    # Pi2(Hub)のIPを環境変数やデフォルトから取得
                    target_ip = payload.get("net_ip", "192.168.1.102") 
                    
                    # ポート出し分け（pi: 5005, usb: 5006）
                    default_port = 5005 if self.hw_type == "pi" else 5006
                    target_port = payload.get("net_port", default_port)
                    
                    print(f"[*] Starting {self.hw_type} stream to {target_ip}:{target_port}")
                    self.start_streaming(target_ip, target_port)
                else:
                    print(f"[*] Stopping {self.hw_type} stream")
                    self.stop_streaming()

    def _streaming_loop(self, dest_ip, port):
        """配信スレッドの実体"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dest_addr = (dest_ip, port)
        
        if self.hw_type == "pi":
            width, height = self.val_res.split('x')
            cmd = [
                "rpicam-vid", "-t", "0", "--inline", "--nopreview",
                "--width", width, "--height", height,
                "--framerate", str(self.val_fps),
                "--codec", "mjpeg", "--flush", "--denoise", "cdn_off",
                "-o", "-"
            ]
        else:
            # USBカメラ: 少し汎用的な設定に戻す
            cmd = [
                "ffmpeg", "-y",
                "-f", "v4l2",
                "-i", self.hw_device,
                "-vf", f"fps={self.val_fps},scale={self.val_res.replace('x', ':')}",
                "-f", "mjpeg", 
                "-q:v", "10", 
                "-tune", "zerolatency", 
                "-flush_packets", "1", # パケットを即座に流す
                "pipe:1"
            ]

        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # ノンブロッキング設定
        for p in [self.process.stdout, self.process.stderr]:
            fd = p.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        buffer = b""
        self.log_msg = f"Started: {self.hw_type} -> {dest_ip}:{port}"

        while not self.stop_event.is_set():
            # エラーログ取得
            try:
                err = self.process.stderr.read(1024)
                if err: self.log_code = err.decode()[-200:]
            except: pass

            # 映像データ取得
            try:
                while True:
                    chunk = self.process.stdout.read(16384)
                    if not chunk: break
                    buffer += chunk
            except: pass

            # フレーム切り出し
            a = buffer.rfind(b'\xff\xd8')
            b = buffer.find(b'\xff\xd9', a)
            
            if a != -1 and b != -1:
                frame = buffer[a:b+2]
                self.wmp.send_large_data(sock, dest_addr, frame, flags=1)
                buffer = buffer[b+2:]
                time.sleep(1.0 / self.val_fps * 0.5) 
            else:
                time.sleep(0.001)

        if self.process:
            self.process.terminate()
            self.process.wait()
        sock.close()

    def start_streaming(self, dest_ip, port):
        """ストリーミング開始"""
        if self.val_status == "streaming": return
        if not dest_ip: return

        self.stop_event.clear()
        self.thread = threading.Thread(target=self._streaming_loop, args=(dest_ip, port))
        self.thread.daemon = True
        self.thread.start()
        self.val_status = "streaming"

    def stop_streaming(self):
        """ストリーミング停止"""
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)
        self.val_status = "idle"
        self.log_msg = "Stopped"