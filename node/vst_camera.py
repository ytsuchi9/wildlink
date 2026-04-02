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
    
    [修正点]
    - 条項15に基づく3段階プロセス終了ロジックの実装
    - 初回フレーム送信時の自動イベント発行（UI連携用）
    - 基底クラスの引数不整合を解消
    """

    def __init__(self, sys_id, role, params, mqtt_client=None, event_callback=None):
        # 基底クラスの初期化（params をそのまま渡すことで自動展開を利用）
        super().__init__(sys_id, role, params, mqtt_client, event_callback)
        
        # --- ハードウェア固有設定 ---
        self.hw_driver = str(self.params.get("hw_driver", "CSI_CAM")).upper()
        self.hw_device = self.params.get("hw_bus_addr") or "/dev/video0" 
        
        # --- ストリーミング設定 ---
        self.val_res = self.params.get("val_res", "320x240")
        self.val_fps = self.params.get("val_fps", 5)
        self.hub_ip = self.params.get("hub_ip", "127.0.0.1")
        
        default_port = 5005 if "CSI" in self.hw_driver else 5006
        self.net_port = int(self.params.get("net_port") or default_port)
        
        # WMP (WildLink Media Protocol) の準備
        from common.wmp_core import WMPHeader
        self.wmp = WMPHeader(node_id=self.sys_id, role=self.vst_role_name, media_type=2)
        
        # 内部制御フラグ
        self.process = None
        self.thread = None
        self.stop_event = threading.Event()

        logger.info(f"[{self.role}] VST_Camera initialized. Driver: {self.hw_driver}")

    def execute_logic(self, payload):
        """
        [WES 2026] Absolute Control 準拠
        基底クラスで更新された self.act_run の真偽値に基づき、
        トグルを排除した絶対的な状態制御を行う。
        """
        # すでに基底クラスの control() 内で self.act_run は更新済み
        
        if self.act_run:
            # 起動リクエストの場合
            if self.val_status == "streaming" and self.thread and self.thread.is_alive():
                logger.info(f"ℹ️ [{self.role}] Already in streaming state. Skipping start.")
                # すでに目的の状態なら、完了報告だけして終了
                self.send_response("completed", log_msg="Stay streaming (No action needed)")
            else:
                logger.info(f"▶️ [{self.role}] Condition met: Starting stream...")
                self.start_streaming()
        else:
            # 停止リクエストの場合
            if self.val_status == "idle":
                logger.info(f"ℹ️ [{self.role}] Already in idle state. Skipping stop.")
                self.send_response("completed", log_msg="Stay idle (No action needed)")
            else:
                logger.info(f"⏹️ [{self.role}] Condition met: Stopping stream...")
                self.stop_streaming()

    def start_streaming(self):
        """
        [WES 2026] ストリーミングスレッドの起動と状態管理の同期
        """
        # 1. 二重起動防止
        if self.thread and self.thread.is_alive():
            logger.info(f"ℹ️ [{self.role}] Stream thread already running.")
            return
            
        # 2. 状態の初期化
        self.stop_event.clear()
        self.val_status = "starting" # まずは 'starting'
        
        # 3. スレッド開始
        self.thread = threading.Thread(target=self._streaming_loop, name=f"Thread-{self.role}")
        self.thread.daemon = True
        self.thread.start()
        
        # 4. 応答とステータス更新
        # ここで 'starting' を報告することで、UIは「処理中」であることを認識できる
        self.send_response("acknowledged", log_msg="Capture process initiated...")
        
        # 5. 内部状態の確定 (loop側で streaming になるまでの繋ぎ)
        # 本来は _streaming_loop 内で最初のパケットを送った直後に 'streaming' に更新するのがベストです
        logger.info(f"🚀 [{self.role}] Stream thread started.")

    def stop_streaming(self):
        """
        [WES 2026 条項15] プロセスを厳格に終了させ、状態を確定させてから応答する。
        """
        if not self.thread or not self.thread.is_alive():
            logger.info(f"ℹ️ [{self.role}] already idle.")
            self.val_status = "idle"
            self.update_status({"val_status": "idle"})
            return

        logger.info(f"⏹️ [{self.role}] Stopping streaming...")
        self.stop_event.set()
            
        if self.process:
            try:
                # 1. 正常終了を試みる
                self.process.terminate()
                try:
                    self.process.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    # 2. 強制終了
                    logger.warning(f"[{self.role}] Process timeout. Killing...")
                    self.process.kill()
                    self.process.wait()
            except Exception as e:
                logger.error(f"[{self.role}] Error during process cleanup: {e}")
            finally:
                self.process = None
            
        # 3. スレッドの完全停止を待機（ここで finally ブロックが実行されるのを待つ）
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

        # 4. 状態の確定を「先」に行う
        self.val_status = "idle"
        self.act_run = False
        
        # 5. DBのステータスを確実に更新（マニフェスト：Absolute Control）
        self.update_status({"val_status": "idle", "act_run": False})
        
        # 6. 最後に完了報告を出す
        self.send_response("completed", log_msg="Stream stopped successfully")
        self.send_event("streaming_stopped")
        logger.info(f"✅ [{self.role}] stop_streaming sequence completed.")

    def _streaming_loop(self):
        """キャプチャ・パケット送信ループ"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dest_addr = (self.hub_ip, self.net_port)
        
        logger.info(f"Dest: {dest_addr}")   # デバッグ用

        # コマンド構築
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
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            fd = self.process.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            buffer = b""
            first_frame_sent = False 

            while not self.stop_event.is_set():
                if self.process.poll() is not None:
                    _, stderr_data = self.process.communicate()
                    err_text = stderr_data.decode().strip() if stderr_data else "Unknown error"
                    raise Exception(f"Process exited unexpectedly: {err_text[:100]}")

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
                        self.wmp.send_large_data(sock, dest_addr, frame)
                        
                        if not first_frame_sent:
                            # [WES 2026] 状態の確定
                            self.val_status = "streaming"
                            self.act_run = True
                            # DB側の状態と completed_at を同期
                            self.update_status({"val_status": "streaming"})
                            self.send_response("completed", log_msg="Streaming started")
                            self.send_event("streaming_started", {"net_port": self.net_port})
                            first_frame_sent = True

                        buffer = buffer[end+2:]
                    else:
                        break
        
        except Exception as e:
            logger.error(f"[{self.role}] Streaming error: {e}")
            self.val_status = "error"
            self.send_response("failed", log_msg=str(e), log_code=500)
            self.send_event("error")
        
        finally:
            # --- 【修正ポイント】終了時のクリーンアップと状態報告 ---
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()

            sock.close()
            
            # 状態を idle に戻し、DB に最終報告
            # 正常終了（stop_eventセット）なら val_status を idle へ
            if self.val_status != "error":
                self.val_status = "idle"
                self.act_run = False
            
            # DB同期（引数あり update_status を使用）
            self.update_status({"val_status": self.val_status, "act_run": self.act_run})
            
            logger.info(f"⏹️ [{self.role}] Streaming loop finished. Status set to: {self.val_status}")

    def stop(self):
        """Node全体の終了時"""
        self.stop_streaming()