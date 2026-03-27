import os
import subprocess
import socket
import time
import fcntl
import threading
from common.vst_base import WildLinkVSTBase

class VST_Camera(WildLinkVSTBase):
    """
    WildLink Event Standard (WES) 2026 準拠
    役割: 指定されたドライバ（CSI/USB）を使用して映像をキャプチャし、
    WMPプロトコルを用いてUDPでストリーミング配信を行う。
    """
    def __init__(self, sys_id, role, params, mqtt_client=None, event_callback=None):
        # 基底クラスの初期化 (sys_id, role, params を渡す)
        super().__init__(sys_id, role, params, mqtt_client, event_callback)
        
        # --- ハードウェア設定 ---
        # MainManagerがDBから取得した config 情報を params 経由で受け取る想定
        self.hw_driver = str(params.get("hw_driver", "CSI_CAM")).upper()
        self.hw_device = params.get("hw_bus_addr") or "/dev/video0" 
        
        # --- 動作設定 ---
        self.val_res = params.get("val_res", "320x240")
        self.val_fps = params.get("val_fps", 5)
        self.hub_ip = params.get("hub_ip", "127.0.0.1")
        
        # ポート番号の自動決定 (CSI=5005, USB=5006)
        default_port = 5005 if "CSI" in self.hw_driver else 5006
        self.dest_port = int(params.get("net_port") or default_port)
        
        # WMP (WildLink Media Protocol) ヘッダーの準備
        from common.wmp_core import WMPHeader
        self.wmp = WMPHeader(node_id=self.sys_id, role=self.role, media_type=2)
        
        # 内部制御フラグ
        self.act_run = False 
        self.process = None
        self.thread = None
        self.stop_event = threading.Event()

    def execute_logic(self, payload):
        """
        コマンド（act_run）に応じたストリーミングの開始・停止制御。
        """
        # 基底クラスの control() により、payload 内の act_run は既に反映済み
        target_run = getattr(self, "act_run", False)

        # 状態に変化がある場合のみ処理を実行
        if target_run:
            self.start_streaming()
        else:
            self.stop_streaming()

    def start_streaming(self):
        """スレッドを起動してストリーミングを開始する"""
        if self.thread and self.thread.is_alive():
            return
            
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._streaming_loop, name=f"Thread-{self.role}")
        self.thread.daemon = True
        self.thread.start()
        
        self.val_status = "streaming"
        self.log_msg = f"Started streaming via {self.hw_driver}"
        self.log_code = 200
        
        # WES 2026: 状態変化をイベントトピックへ通知
        self.send_event("streaming_started")

    def stop_streaming(self):
        """ストリーミングを停止し、プロセスをクリーンアップする"""
        if not self.stop_event.is_set():
            self.stop_event.set()
            
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            
        self.val_status = "idle"
        self.log_msg = "Stream stopped"
        self.act_run = False
        
        # WES 2026: 停止をイベントトピックへ通知
        self.send_event("streaming_stopped")

    def _streaming_loop(self):
        """映像キャプチャとUDP送信のメインループ"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dest_addr = (self.hub_ip, self.dest_port)
        
        # ドライバごとのコマンド構築
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
            
            # パイプのノンブロッキング設定
            fd = self.process.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            buffer = b""
            while not self.stop_event.is_set():
                try:
                    chunk = self.process.stdout.read(65536)
                    if chunk:
                        buffer += chunk
                    elif self.process.poll() is not None:
                        break
                except (BlockingIOError, TypeError):
                    time.sleep(0.005)
                    continue

                # JPEGフレームの切り出し (SOI: \xff\xd8, EOI: \xff\xd9)
                while True:
                    start = buffer.find(b'\xff\xd8')
                    end = buffer.find(b'\xff\xd9', start)
                    if start != -1 and end != -1:
                        frame = buffer[start:end+2]
                        # WMPプロトコルでパケット分割送信
                        if self.act_run:
                            self.wmp.send_large_data(sock, dest_addr, frame)
                        buffer = buffer[end+2:]
                    else:
                        break
                
                # バッファ溢れ防止
                if len(buffer) > 2000000:
                    buffer = b""
                    
        except Exception as e:
            self.val_status = "error"
            self.log_msg = f"Stream error: {str(e)}"
            self.log_code = 500
            self.send_event("error")
        finally:
            if self.process:
                self.process.terminate()
            sock.close()

    def stop(self):
        """ノード停止時のクリーンアップ"""
        self.stop_streaming()