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
        super().__init__(sys_id, role, params, mqtt_client, event_callback)
        
        # --- ハードウェア設定 ---
        self.hw_driver = str(params.get("hw_driver", "CSI_CAM")).upper()
        self.hw_device = params.get("hw_bus_addr") or "/dev/video0" 
        
        # --- 動作設定 ---
        self.val_res = params.get("val_res", "320x240")
        self.val_fps = params.get("val_fps", 5)
        self.hub_ip = params.get("hub_ip", "127.0.0.1")
        
        default_port = 5005 if "CSI" in self.hw_driver else 5006
        self.dest_port = int(params.get("net_port") or default_port)
        
        # WMP (WildLink Media Protocol) ヘッダー
        from common.wmp_core import WMPHeader
        self.wmp = WMPHeader(node_id=self.sys_id, role=self.role, media_type=2)
        
        # 内部制御
        self.act_run = False 
        self.process = None
        self.thread = None
        self.stop_event = threading.Event()

    def control(self, payload):
        """
        [WES 2026] 命令を受けて実行し、完了を報告する
        """
        # 1. 実行するコマンドIDを保持
        self.ref_cmd_id = payload.get("cmd_id")
        
        # 2. 親クラスの処理（act_run などの変数更新）を呼ぶ
        super().control(payload)
        
        # 3. 実際の動作（配信開始/停止）
        target_run = payload.get("act_run", False)
        if target_run:
            self.start_streaming()
            # ここでは send_response を呼ばず、実際の成功を待つ
        else:
            self.stop_streaming()
            self.send_response("completed", log_msg="Stream stopped by command")

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
        
        # [WES 2026] 配信が正常に開始されたことを完了報告として送信
        # これにより DB の completed_at が更新される
        self.send_response("completed")
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
        
        # 停止状態を報告
        self.send_response("idle")
        self.send_event("streaming_stopped")

    def _streaming_loop(self):
        """映像キャプチャとUDP送信のメインループ"""
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
            # stderr=subprocess.PIPE を追加してエラーログを拾えるようにする
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 非ブロック設定
            fd = self.process.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            buffer = b""
            first_frame_sent = False # 💡 成功フラグ

            while not self.stop_event.is_set():
                # 途中でプロセスが死んでいないかチェック
                if self.process.poll() is not None:
                    # エラー出力を取得
                    err_msg = self.process.stderr.read().decode().strip()
                    raise Exception(f"Process terminated: {err_msg[:100]}")

                try:
                    chunk = self.process.stdout.read(65536)
                    if not chunk:
                        time.sleep(0.01)
                        continue
                    buffer += chunk
                except (BlockingIOError, TypeError):
                    time.sleep(0.005)
                    continue

                while True:
                    start = buffer.find(b'\xff\xd8')
                    end = buffer.find(b'\xff\xd9', start)
                    if start != -1 and end != -1:
                        frame = buffer[start:end+2]
                        if self.act_run:
                            self.wmp.send_large_data(sock, dest_addr, frame)
                            
                            # 💡 最初の1枚が送れたら「完了(completed)」を報告
                            if not first_frame_sent:
                                self.val_status = "streaming"
                                self.send_response("completed", log_msg="Streaming started successfully")
                                self.send_event("streaming_started")
                                first_frame_sent = True

                        buffer = buffer[end+2:]
                    else:
                        break
        
        except Exception as e:
            self.val_status = "error"
            self.log_msg = str(e)
            # 💡 失敗したことを Hub に伝える
            self.send_response("failed", log_msg=self.log_msg)
            self.send_event("error")
        finally:
            if self.process:
                self.process.terminate()
            sock.close()

    def stop(self):
        """ノード停止時のクリーンアップ"""
        self.stop_streaming()