import os
import subprocess
import socket
import time
import fcntl
import threading
from common.vst_base import WildLinkVSTBase
from common.logger_config import get_logger

logger = get_logger("vst_camera.py")

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

        logger.info(f"Driver: {self.hw_driver}")

    def control(self, payload):
        """
        [WES 2026] 命令を受けて実行し、完了を報告する
        """
        # 1. 実行するコマンドIDを保持
        self.ref_cmd_id = payload.get("cmd_id", 0)
        
        # 2. 親クラスの処理（act_run などの変数更新と Acknowledge 送信を想定）
        super().control(payload)
        
        target_run = payload.get("act_run", False)

        # 3. 実際の動作（配信開始/停止）
        if target_run:
            if self.act_run and self.thread and self.thread.is_alive():
                # 既に配信中の場合は、何もせず「完了」を報告
                logger.info(f"ℹ️ [{self.role}] Already streaming. Skipping start.")
                self.send_response("completed", log_msg="Already streaming")
            else:
                # 配信開始（完了報告は最初のフレーム送信時に _streaming_loop 内で行う）
                self.start_streaming()
        else:
            if not self.act_run:
                # 既に停止している場合は、何もせず「完了」を報告
                logger.info(f"ℹ️ [{self.role}] Already idle. Skipping stop.")
                self.send_response("completed", log_msg="Already stopped")
            else:
                # 配信停止
                self.stop_streaming()
                # stop_streaming の中で send_response("completed") を呼ぶように変更したため、ここでは呼ばない

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
        logger.info(f"Stopping stream for {self.role}...")
        
        if not self.stop_event.is_set():
            self.stop_event.set()
            
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.5)
            except Exception:
                if self.process:
                    self.process.kill()
            self.process = None
            
        # スレッドの終了を待つ（デッドロック防止のためタイムアウト付き）
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

        # 状態の更新
        self.val_status = "idle"
        self.act_run = False
        self.log_msg = "Stream stopped"
        
        # [WES 2026] 停止完了を報告
        # 'idle' という独自ステータスではなく、コマンドに対する結果として 'completed' を送る
        self.send_response("completed", log_msg=self.log_msg)
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