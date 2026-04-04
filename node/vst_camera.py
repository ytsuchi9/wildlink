import os
import subprocess
import socket
import time
import fcntl
import threading
from common.vst_base import WildLinkVSTBase
from common.logger_config import get_logger

logger = get_logger("vst_camera")

class VST_Camera(WildLinkVSTBase):
    """
    WildLink Event Standard (WES) 2026 準拠
    役割: 映像キャプチャ(CSI/USB)およびWMPプロトコルによるUDP配信。
    """

    def __init__(self, sys_id, role, params, mqtt_client=None, event_callback=None):
        super().__init__(sys_id, role, params, mqtt_client, event_callback)
        
        # --- ハードウェア固有設定 ---
        self.hw_driver = str(self.params.get("hw_driver", "CSI_CAM")).upper()
        self.hw_device = self.params.get("hw_bus_addr") or "/dev/video0" 
        
        # --- ストリーミング設定 ---
        self.val_res = self.params.get("val_res", "320x240")
        self.val_fps = self.params.get("val_fps", 5)
        
        # [WES 2026 改修] MainManagerから注入された net_hub_ip を取得
        self.net_hub_ip = self.params.get("net_hub_ip", "127.0.0.1")
        
        default_port = 5005 if "CSI" in self.hw_driver else 5006
        self.net_port = int(self.params.get("net_port") or default_port)
        
        # WMP (WildLink Media Protocol) の準備
        from common.wmp_core import WMPHeader
        self.wmp = WMPHeader(node_id=self.sys_id, role=self.vst_role_name, media_type=2)
        
        # 内部制御フラグ
        self.process = None
        self.thread = None
        self.stop_event = threading.Event()

        logger.info(f"[{self.role}] VST_Camera initialized. Driver: {self.hw_driver}, Dest: {self.net_hub_ip}:{self.net_port}")

    def execute_logic(self, payload):
        # (ロジックは現状のままで完璧です)
        if self.act_run:
            if self.val_status == "streaming" and self.thread and self.thread.is_alive():
                logger.info(f"ℹ️ [{self.role}] Already in streaming state. Skipping start.")
                self.send_response("completed", log_msg="Stay streaming (No action needed)", log_code=200)
            else:
                logger.info(f"▶️ [{self.role}] Condition met: Starting stream...")
                self.start_streaming()
        else:
            if self.val_status == "idle":
                logger.info(f"ℹ️ [{self.role}] Already in idle state. Skipping stop.")
                self.send_response("completed", log_msg="Stay idle (No action needed)", log_code=200)
            else:
                logger.info(f"⏹️ [{self.role}] Condition met: Stopping stream...")
                self.stop_streaming()

    def start_streaming(self):
        if self.thread and self.thread.is_alive():
            logger.info(f"ℹ️ [{self.role}] Stream thread already running.")
            return
            
        self.stop_event.clear()
        self.val_status = "starting"
        
        self.thread = threading.Thread(target=self._streaming_loop, name=f"Thread-{self.role}")
        self.thread.daemon = True
        self.thread.start()
        
        self.send_response("acknowledged", log_msg="Capture process initiated...", log_code=202)
        logger.info(f"🚀 [{self.role}] Stream thread started.")

    def stop_streaming(self):
        """[WES 2026] 配信を停止し、コマンドを完了させる"""
        if not self.thread or not self.thread.is_alive():
            logger.info(f"ℹ️ [{self.role}] already idle.")
            self.act_run = False
            self.update_status(val_status="idle")
            # 既に止まっている場合でも、コマンドが来ていれば完了を返す
            if hasattr(self, 'ref_cmd_id') and self.ref_cmd_id:
                self.send_response("completed", log_msg="Already stopped", log_code=200)
            return

        logger.info(f"⏹️ [{self.role}] Stopping streaming...")
        self.stop_event.set()
            
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)

        # プロセス強制終了（念のため）
        if self.process and self.process.poll() is None:
            self.process.terminate() # killの前に優しくterminate
            try:
                self.process.wait(timeout=2.0) # ★これが必要
            except subprocess.TimeoutExpired:
                self.process.kill() # 2秒待っても死ななければkill
                self.process.wait() # killの後もwaitが必要
            self.process = None

        self.act_run = False
        self.update_status(val_status="idle", log_code=200)
        
        # 🌟 停止コマンドを正常に「完了」させる
        self.send_response("completed", log_msg="Stream stopped successfully", log_code=200)
        self.send_event("streaming_stopped")
        
        # 最後にIDをクリア
        self.ref_cmd_id = None

    def _streaming_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dest_addr = (self.net_hub_ip, self.net_port)
        
        # PiZeroの負荷を考慮し、読み取りバッファサイズを調整 (3/13安定版に近い設定)
        READ_SIZE = 16384 
        
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
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
            # --- 🚀 修正ポイント1: Popen直後の生存確認 ---
            try:
                # 0.8秒だけ待つ。死ぬならここで死ぬ。
                self.process.wait(timeout=0.8)
                # ここに来る＝即死した
                stderr_output = self.process.stderr.read().decode('utf-8', errors='ignore')
                self.send_response("error", log_msg=f"Process died: {stderr_output[:100]}", log_code=500)
                return 
            except subprocess.TimeoutExpired:
                # 正常：まだ動いている
                pass
            # ----------------------------------------
            fd = self.process.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            buffer = b""
            first_frame_sent = False 

            while not self.stop_event.is_set():
                if self.process.poll() is not None:
                    break

                try:
                    chunk = self.process.stdout.read(READ_SIZE)
                    if not chunk:
                        time.sleep(0.01)
                        continue
                    buffer += chunk
                except (BlockingIOError, TypeError):
                    time.sleep(0.005)
                    continue

                # 🌟 修正版：サイズ・ヒューリスティックによる切り出し
                start = buffer.find(b'\xff\xd8')
                if start != -1:
                    eoi_pos = buffer.find(b'\xff\xd9', start)
                    
                    if eoi_pos != -1:
                        frame_size = (eoi_pos + 2) - start
                        
                        if frame_size > 5000:
                            # ✅ 本物のフレーム：送信してバッファから消す
                            frame = buffer[start:eoi_pos+2]
                            self.wmp.send_large_data(sock, dest_addr, frame)
                            
                            if not first_frame_sent:
                                self.act_run = True
                                self.update_status(val_status="streaming", log_code=200)
                                # 👇 ここで send_response ("completed") を呼ぶと、
                                # STARTコマンドが即座に終わったとみなされ、管理側との同期でストリームが乱れる原因になります。
                                # 「受け付けた」という acknowledged だけに留めるか、
                                # ストリーム開始は status 更新のみにするのが安全です。
                                # self.send_response("completed", ...) は削除または慎重に。
                                # 👇 cmd_status="completed" を送るのをやめ、イベント通知のみにする
                                self.send_event("streaming_started")
                                first_frame_sent = True

                            buffer = buffer[eoi_pos+2:]
                        else:
                            # 🗑️ ゴミ（サムネイル等）：バッファから消して、次を探す
                            # これを入れないと、startがずっとゴミの先頭を指し続けてしまいます
                            buffer = buffer[eoi_pos+2:]
                            continue # 次のループへ（もう一度 buffer.find をさせる）

        except Exception as e:
            logger.error(f"[{self.role}] Streaming error: {e}")
            self.send_response("error", log_msg=str(e), log_code=500)
        finally:
            # 終了処理は一括してfinallyで行う
            if self.process and self.process.poll() is None:
                self.process.terminate()
                self.process.wait() # ★ここでもwait
            sock.close()

    def stop(self):
        """Node全体の終了時"""
        self.stop_streaming()