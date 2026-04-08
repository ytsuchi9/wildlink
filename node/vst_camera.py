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
    役割: 映像キャプチャ(CSI/USB)およびWMPプロトコルによるUDP配信専任モジュール。
    
    【WES 2026: 状態遷移の厳密化】
    - コマンド受信直後に 'acknowledged' を返却し、DBに受領時刻(acked_at)を刻みます。
    - 実際のストリーム開始・停止が完了した時点で 'completed' を返却します。
    """

    def __init__(self, sys_id, role, params, mqtt_client=None, event_callback=None):
        super().__init__(sys_id, role, params, mqtt_client, event_callback)
        
        # --- ハードウェア固有設定 ---
        self.hw_driver = str(self.params.get("hw_driver", "CSI_CAM")).upper()
        self.hw_device = self.params.get("hw_bus_addr") or "/dev/video0" 
        
        # --- ストリーミング設定 ---
        self.val_res = self.params.get("val_res", "320x240")
        self.val_fps = self.params.get("val_fps", 5)
        
        # [WES 2026] MainManagerから注入された net_hub_ip を取得
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
        """
        コマンド受信時の振り分けロジック
        WES 2026に基づき、重い処理の前にまず ACK を返します。
        """
        # 🌟 [追加] 処理を開始する前に、まずコマンドの受領をHubへ報告 (acked_atを刻む)
        cmd_id = payload.get('cmd_id')
        if cmd_id:
            logger.info(f"📥 [{self.role}] Acknowledging command ID: {cmd_id}")
            self.send_response("acknowledged", log_msg="Command received. Starting execution...")

        if self.act_run:
            if self.val_status == "streaming" and self.thread and self.thread.is_alive():
                logger.info(f"ℹ️ [{self.role}] Already in streaming state.")
                self.send_response("completed", log_msg="Stay streaming (No action needed)", log_code=200)
            else:
                logger.info(f"▶️ [{self.role}] Condition met: Starting stream...")
                self.start_streaming()
        else:
            if self.val_status == "idle":
                logger.info(f"ℹ️ [{self.role}] Already in idle state.")
                self.send_response("completed", log_msg="Stay idle (No action needed)", log_code=200)
            else:
                logger.info(f"⏹️ [{self.role}] Condition met: Stopping stream...")
                self.stop_streaming()

    def start_streaming(self):
        """ ストリーミング開始処理（スレッド起動のみに専念） """
        if self.thread and self.thread.is_alive():
            # 既に動いている場合は、即座に完了を返して良い
            self.send_response("completed", log_msg="Stay streaming (No action needed)", log_code=200)
            return
            
        self.stop_event.clear()
        self.val_status = "starting"
        
        # 🌟 ここでは 'completed' を送らず、スレッドに成否判定を委ねる
        self.thread = threading.Thread(target=self._streaming_loop, name=f"Thread-{self.role}")
        self.thread.daemon = True
        self.thread.start()
        logger.info(f"⏳ [{self.role}] Stream thread launched. Waiting for hardware response...")

    def stop_streaming(self):
        """ ストリーミング停止処理 """
        if not self.thread or not self.thread.is_alive():
            logger.info(f"ℹ️ [{self.role}] already idle.")
            self.act_run = False
            self.update_status(val_status="idle")
            # 停止命令に対して「すでに止まっている」として完了を返す
            self.send_response("completed", log_msg="Already stopped", log_code=200)
            return

        logger.info(f"⏹️ [{self.role}] Stopping streaming...")
        self.stop_event.set()
            
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)

        # プロセス強制終了
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None

        self.act_run = False
        self.update_status(val_status="idle", log_code=200)
        
        # 🌟 停止処理が正常に完了したことをHubに報告
        self.send_response("completed", log_msg="Stream stopped successfully", log_code=200)
        self.send_event("streaming_stopped")
        
        # 最後にIDをクリア（基底クラス側の管理を優先）
        self.ref_cmd_id = None

    def _streaming_loop(self):
        """ 映像ストリーミングのメインループ（判定ロジック強化版） """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dest_addr = (self.net_hub_ip, self.net_port)
        READ_SIZE = 16384 
        
        # コマンドIDを保持（ループ内で報告に使うため）
        current_cmd_id = self.ref_cmd_id

        # --- [コマンド組み立て部分は変更なし] ---
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
            
            # 🌟 [検証] プロセスが即死していないか短時間待機
            try:
                self.process.wait(timeout=1.0)
                # ここに到達＝プロセスが終了してしまった
                stderr_output = self.process.stderr.read().decode('utf-8', errors='ignore')
                logger.error(f"[{self.role}] Process died early: {stderr_output[:100]}")
                
                # ❌ コマンド失敗を報告
                # 🌟 ステータスを先に 'error' に変更してからレスポンスを送る
                self.val_status = "error" 
                self.send_response("error", log_msg=f"Device error: {stderr_output[:50]}", log_code=500)
                return 
            except subprocess.TimeoutExpired:
                # タイムアウト＝プロセスが生存している（正常の兆候）
                pass
                
            # ノンブロッキング設定
            fd = self.process.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            buffer = b""
            first_frame_sent = False 

            while not self.stop_event.is_set():
                if self.process.poll() is not None:
                    # 配信中にプロセスが落ちた場合
                    if not first_frame_sent:
                         self.val_status = "error" # 🌟 追加
                         self.send_response("error", log_msg="Process died before stream", log_code=500)
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

                start = buffer.find(b'\xff\xd8')
                if start != -1:
                    eoi_pos = buffer.find(b'\xff\xd9', start)
                    if eoi_pos != -1:
                        frame_size = (eoi_pos + 2) - start
                        if frame_size > 100: # 最小サイズチェック
                            frame = buffer[start:eoi_pos+2]
                            self.wmp.send_large_data(sock, dest_addr, frame)
                            
                            # 🌟 [成功確定] 最初のフレームが送れたら 'completed' を報告
                            if not first_frame_sent:
                                # 🌟 成功確定：ステータスを streaming にして完了報告
                                logger.info(f"✨ [{self.role}] First frame sent. Finalizing command {current_cmd_id}")
                                self.val_status = "streaming"
                                self.send_response("completed", log_msg="Stream started", log_code=200)
                                self.send_event("stream_ready")
                                first_frame_sent = True

                            buffer = buffer[eoi_pos+2:]
                        else:
                            buffer = buffer[eoi_pos+2:]
                            continue

        except Exception as e:
            logger.error(f"[{self.role}] Streaming error: {e}")
            self.send_response("error", log_msg=f"Exception: {str(e)}", log_code=500)
            self.update_status(val_status="error")
            self.send_event("streaming_error")
        finally:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                self.process.wait() 
            sock.close()

    def stop(self):
        """ Node全体の終了時 """
        self.stop_streaming()