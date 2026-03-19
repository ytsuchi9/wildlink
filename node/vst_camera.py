import os
import subprocess
import socket
import time
import fcntl
import threading
from common.vst_base import WildLinkVSTBase

class VST_Camera(WildLinkVSTBase):
    def __init__(self, role, params, mqtt, event_callback=None, config=None):
        # 1. ベースクラスの初期化
        super().__init__(role, params, mqtt, event_callback)
        self.config = config or {}
        
        # 2026年仕様: sys_id は環境変数またはconfigから厳密に取得
        self.sys_id = self.config.get("sys_id") or os.getenv("SYS_ID", "node_001")

        # 2. ハードウェア・ネットワーク設定の反映
        # DBの hw_driver, hw_bus_addr を優先使用
        self.hw_driver = str(self.config.get("hw_driver", "CSI_CAM")).upper()
        self.hw_device = self.config.get("hw_bus_addr") or "/dev/video0" 

        self.val_res = params.get("val_res", "320x240")
        self.val_fps = params.get("val_fps", 5)
        
        # ハブのIPとポート
        self.hub_ip = params.get("hub_ip", "192.168.1.102")
        # ポート設定がなければドライバ毎のデフォルト(CSI:5005, USB:5006)
        default_port = 5005 if self.hw_driver == "CSI_CAM" else 5006
        self.dest_port = int(params.get("net_port") or default_port)
        
        # 3. WMPプロトコルヘッダー (2026仕様: roleを付加)
        from common.wmp_core import WMPHeader
        # node_id に加え、どの役割の映像かを識別できるよう role を渡す
        self.wmp = WMPHeader(node_id=self.sys_id, role=self.role, media_type=2)
        
        # 4. 内部状態
        self.act_run = False 
        self.val_status = "idle"
        self.process = None
        self.thread = None
        self.stop_event = threading.Event()
        
        print(f"📷 [{self.role}] Initialized: Node={self.sys_id}, Driver={self.hw_driver}, Port={self.dest_port}")

    @property
    def status_dict(self):
        """WebUIへのステータス報告用辞書"""
        return {
            "vst_role_name": self.role, # 💡 役割名を明記
            "val_status": self.val_status,
            "act_run": self.act_run,
            "log_msg": f"Streaming via {self.hw_driver} on {self.hw_device}" if self.act_run else "Ready"
        }

    def execute_logic(self, payload):
        """Manager(MQTT)からの命令を処理"""
        # payload['action'] が 'start'/'stop' か、payload['act_run'] が True/False かをチェック
        target_run = payload.get("act_run")
        if target_run is None and "action" in payload:
            target_run = (payload["action"] == "start")

        if target_run is not None and self.act_run != target_run:
            self.act_run = target_run
            if self.act_run:
                self.start_streaming()
            else:
                self.stop_streaming()

    def start_streaming(self):
        if self.thread and self.thread.is_alive():
            return
            
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._streaming_loop, name=f"Thread-{self.role}")
        self.thread.daemon = True
        self.thread.start()
        self.val_status = "streaming"
        # 💡 親のManagerに状態変化を即時通知（MQTT経由でDBへ）
        self.notify_manager()

    def stop_streaming(self):
        self.stop_event.set()
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=1.0)
            except:
                self.process.kill()
            self.process = None
        
        self.val_status = "idle"
        self.notify_manager()
        print(f"⏹️ [{self.role}] Stream stopped.")

    def _streaming_loop(self):
        """キャプチャ & UDP送信ループ"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dest_addr = (self.hub_ip, self.dest_port)
        
        # 1. コマンド構築
        if "CSI" in self.hw_driver:
            w, h = self.val_res.split('x')
            cmd = ["rpicam-vid", "-t", "0", "--inline", "--nopreview",
                   "--width", w, "--height", h, "--framerate", str(self.val_fps),
                   "--codec", "mjpeg", "--flush", "-o", "-"]
        else:
            # USBカメラ/V4L2ドライバ用
            cmd = ["ffmpeg", "-y", "-f", "v4l2", "-input_format", "mjpeg",
                   "-video_size", self.val_res, "-framerate", str(self.val_fps),
                   "-i", self.hw_device, "-c:v", "copy", "-f", "mjpeg", "-an", "pipe:1"]

        try:
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            
            # パイプをノンブロッキング設定
            fd = self.process.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            buffer = b""
            while not self.stop_event.is_set():
                try:
                    chunk = self.process.stdout.read(65536) # 少し大きめに読み込み
                    if chunk:
                        buffer += chunk
                    elif self.process.poll() is not None:
                        break
                except (BlockingIOError, TypeError):
                    time.sleep(0.005)
                    continue

                # JPEGフレーム切り出し
                while True:
                    start = buffer.find(b'\xff\xd8')
                    end = buffer.find(b'\xff\xd9', start)
                    
                    if start != -1 and end != -1:
                        frame = buffer[start:end+2]
                        if self.act_run:
                            # 💡 ヘッダーに role 情報を載せて送信
                            self.wmp.send_large_data(sock, dest_addr, frame)
                        buffer = buffer[end+2:]
                    else:
                        break
                
                # バッファ溢れ防止
                if len(buffer) > 2000000: buffer = b""

        except Exception as e:
            print(f"❌ [{self.role}] Runtime Error: {e}")
            self.val_status = "error"
        finally:
            if self.process: self.process.terminate()
            sock.close()

    def stop(self):
        self.stop_streaming()