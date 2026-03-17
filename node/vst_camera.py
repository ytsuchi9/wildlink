import os
import subprocess
import socket
import time
import fcntl
import threading
from common.vst_base import WildLinkVSTBase

class VST_Camera(WildLinkVSTBase):
    def __init__(self, role, params, mqtt, event_callback=None, config=None):
        # ベースクラスの初期化（sys_idの保持など）
        super().__init__(role, params, mqtt, event_callback)
        self.config = config or {}
        
        # 💡 重要：ベースクラスやManagerから引き継いだ sys_id を使用する
        # もしベースクラスで保持していない場合は self.sys_id = params.get("sys_id", "node_001") 等で補完
        self.sys_id = getattr(self, 'sys_id', os.getenv("SYS_ID", "node_001"))

        # 💡 DB設定からの反映
        self.hw_driver = self.config.get("hw_driver", "CSI_CAM")
        # デバイスパス (例: /dev/video0)
        self.hw_device = self.config.get("hw_bus_addr") or "/dev/video0" 

        self.val_res = params.get("val_res", "320x240")
        self.val_fps = params.get("val_fps", 5)
        
        # ネットワーク設定
        self.hub_ip = params.get("hub_ip", "192.168.1.102")
        # ドライバごとにデフォルトポートを変える（競合防止）
        default_port = 5005 if self.hw_driver == "CSI_CAM" else 5006
        self.dest_port = int(params.get("net_port", default_port))
        
        # WMPプロトコルヘッダー
        from common.wmp_core import WMPHeader
        # 💡 修正：node_id を固定値から self.sys_id に変更
        self.wmp = WMPHeader(node_id=self.sys_id, media_type=2)
        
        # 状態管理
        self.act_run = False 
        self.val_status = "idle"
        self.process = None
        self.thread = None
        self.stop_event = threading.Event()
        
        print(f"📷 [{self.role}] Camera VST Ready (Node: {self.sys_id} / Driver: {self.hw_driver})")

    @property
    def status_dict(self):
        return {
            "val_status": self.val_status,
            "act_run": self.act_run,
            "log_msg": f"Streaming via {self.hw_driver}" if self.act_run else "Ready"
        }

    def execute_logic(self, payload):
        """Managerからの命令(act_run)を処理"""
        if "act_run" in payload:
            new_run = payload["act_run"]
            if self.act_run != new_run:
                self.act_run = new_run
                if self.act_run:
                    self.start_streaming()
                else:
                    self.stop_streaming()

    def start_streaming(self):
        """ストリーミング開始：スレッドとプロセスを起動"""
        if self.thread and self.thread.is_alive():
            print(f"⚠️ [{self.role}] Already streaming.")
            return
            
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._streaming_loop)
        self.thread.daemon = True
        self.thread.start()
        self.val_status = "streaming"
        print(f"🚀 [{self.role}] Streaming started (Port: {self.dest_port})")

    def stop_streaming(self):
        """ストリーミング停止：プロセスを確実に殺してデバイスを解放"""
        self.stop_event.set()
        if self.process:
            # 優しく終了を試みる
            self.process.terminate()
            try:
                self.process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                # 死ななければ強制終了
                self.process.kill()
            self.process = None
        
        self.val_status = "idle"
        print(f"⏹️ [{self.role}] Streaming stopped and device released.")

    def _streaming_loop(self):
        """実際のキャプチャと送信を行うサブスレッド"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dest_addr = (self.hub_ip, self.dest_port)
        
        # 1. コマンド構築
        if self.hw_driver == "CSI_CAM":
            w, h = self.val_res.split('x')
            cmd = ["rpicam-vid", "-t", "0", "--inline", "--nopreview",
                   "--width", w, "--height", h, "--framerate", str(self.val_fps),
                   "--codec", "mjpeg", "--flush", "-o", "-"]
        else:
            # USBカメラ用 (ffmpeg)
            cmd = ["ffmpeg", "-y", "-f", "v4l2", "-input_format", "mjpeg",
                   "-video_size", self.val_res, "-framerate", str(self.val_fps),
                   "-i", self.hw_device, "-c:v", "copy", "-f", "mjpeg", "-an", "pipe:1"]

        try:
            # 2. プロセス起動
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            
            # 3. パイプをノンブロッキングに設定
            fd = self.process.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            buffer = b""
            while not self.stop_event.is_set():
                try:
                    chunk = self.process.stdout.read(32768)
                    if chunk:
                        buffer += chunk
                    else:
                        if self.process.poll() is not None:
                            break
                        time.sleep(0.01)
                except (BlockingIOError, TypeError):
                    time.sleep(0.01)
                    continue

                # 4. JPEGフレームの切り出し (FFD8...FFD9)
                while True:
                    start = buffer.find(b'\xff\xd8')
                    end = buffer.find(b'\xff\xd9', start)
                    
                    if start != -1 and end != -1:
                        frame = buffer[start:end+2]
                        # 配信フラグが立っている間のみ送信
                        if self.act_run:
                            # 💡 wmpは __init__ で node_id=self.sys_id を設定済み
                            self.wmp.send_large_data(sock, dest_addr, frame, flags=1)
                        
                        buffer = buffer[end+2:]
                    else:
                        break
                
                # 異常なバッファ溜まりを防止
                if len(buffer) > 1000000:
                    buffer = b""

        except Exception as e:
            print(f"❌ [{self.role}] Runtime Error: {e}")
        finally:
            # 5. クリーンアップ
            if self.process:
                self.process.terminate()
            sock.close()
            print(f"🧹 [{self.role}] Loop finished.")

    def stop(self):
        """Managerのリロード時に呼ばれる"""
        self.stop_streaming()