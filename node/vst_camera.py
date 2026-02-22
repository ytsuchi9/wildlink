import sys
import os
import subprocess
import socket
import time
import fcntl
import threading

class VST_Camera:
    def __init__(self, role, params, mqtt):
        self.role = role          # DBの vst_type (cam_main, cam_sub 等)
        self.params = params      # DBの val_params
        self.mqtt = mqtt          # MainManager共通のMQTTクライアント
        
        # --- DB設定の反映 ---
        # 役割名からデバイスを判断
        if self.role == "cam_main":
            self.hw_type = "pi"
            self.hw_device = None
        else:
            self.hw_type = "usb"
            self.hw_device = "/dev/video0" 

        self.val_res = params.get("val_res", "320x240")
        self.val_fps = params.get("val_fps", 5)
        self.val_status = "idle"
        
        # --- 配信・ネットワーク関連 ---
        # wmp_core が common フォルダにある前提のパス解決は済んでいるものとします
        from common.wmp_core import WMPHeader
        self.wmp = WMPHeader(node_id="node_001", media_type=2)
        
        self.process = None
        self.stop_event = threading.Event()
        self.thread = None

    def poll(self):
        """
        MainManagerのループから毎秒呼ばれる。
        将来的に、ここでカメラの生存確認や
        MQTTからの「配信停止命令」をチェックするロジックを入れることができます。
        """
        pass

    def control(self, payload):
        """
        MQTT経由などで外部から「開始/停止」を命じられた時の窓口
        """
        if "act_run" in payload:
            if payload["act_run"]:
                target_ip = payload.get("net_ip", "192.168.1.102") 
                default_port = 5005 if self.hw_type == "pi" else 5006
                target_port = payload.get("net_port", default_port)
                self.start_streaming(target_ip, target_port)
            else:
                self.stop_streaming()

    def _streaming_loop(self, dest_ip, port):
        print(f"DEBUG: Executing command for {self.hw_type}...") # これを追加
        """(昨日いただいた配信ロジック本体)"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dest_addr = (dest_ip, port)
        
        # コマンド生成
        if self.hw_type == "pi":
            width, height = self.val_res.split('x')
            cmd = [
                "rpicam-vid", "-t", "0", "--inline", "--nopreview",
                "--width", width, "--height", height,
                "--framerate", str(self.val_fps),
                "--codec", "mjpeg", "--flush", "--denoise", "cdn_off",
                "--shutter", "20000", "--awbgains", "1.5,1.5", # ★ 露出とWBを固定（初期化をスキップ）
                "-o", "-"
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-f", "v4l2", "-i", self.hw_device,
                "-vf", f"fps={self.val_fps},scale={self.val_res.replace('x', ':')}",
                "-f", "mjpeg", "-q:v", "10", "-tune", "zerolatency", 
                "-flush_packets", "1", "pipe:1"
            ]
            print(f"DEBUG: Full Command: {' '.join(cmd)}") # これも追加

        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # ノンブロッキング設定
        for p in [self.process.stdout, self.process.stderr]:
            fd = p.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        buffer = b""
        print(f"✅ [{self.role}] Streaming started to {dest_ip}:{port}")

        while not self.stop_event.is_set():
            # 映像データ取得
            try:
                while True:
                    chunk = self.process.stdout.read(16384)
                    if not chunk: break
                    buffer += chunk
            except: pass

            # フレーム切り出し (MJPEG)
            a = buffer.rfind(b'\xff\xd8')
            b = buffer.find(b'\xff\xd9', a)
            
            if a != -1 and b != -1:
                frame = buffer[a:b+2]
                # WMPパケットとして送信
                self.wmp.send_large_data(sock, dest_addr, frame, flags=1)
                buffer = buffer[b+2:]
                time.sleep(1.0 / self.val_fps * 0.5) 
            else:
                time.sleep(0.001)

        if self.process:
            self.process.terminate()
            self.process.wait()
        sock.close()
        print(f"🛑 [{self.role}] Streaming stopped.")

    def start_streaming(self, dest_ip, port):
        if self.val_status == "streaming": return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._streaming_loop, args=(dest_ip, port))
        self.thread.daemon = True
        self.thread.start()
        self.val_status = "streaming"

    def stop_streaming(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)
        self.val_status = "idle"