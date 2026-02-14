import socket
import sys
import os
import threading
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from dotenv import load_dotenv

# --- パス解決 & 環境変数 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
# /opt/wildlink/hub -> /opt/wildlink
wildlink_root = os.path.dirname(current_dir)
common_path = os.path.join(wildlink_root, "common")
sys.path.append(common_path)

# .env の読み込み
load_dotenv(os.path.join(wildlink_root, ".env"))

try:
    from wmp_core import WMPHeader
    print("✅ Success: wmp_core found from common folder!")
except ImportError:
    print("❌ Error: wmp_core not found.")
    sys.exit(1)

# 最新のフレームを保持するグローバル変数
latest_frame = None
frame_lock = threading.Lock()

# --- HTTP MJPEG 配信サーバー ---
class StreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            try:
                while True:
                    with frame_lock:
                        if latest_frame is None:
                            continue
                        frame = latest_frame
                    
                    self.wfile.write(b'--frame\r\n')
                    self.send_header('Content-type', 'image/jpeg')
                    self.send_header('Content-length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                # クライアントが切断してもサーバーを止めない
                pass
        else:
            self.send_response(404)
            self.end_headers()

def run_http_server(port=8080):
    server = HTTPServer(('0.0.0.0', port), StreamHandler)
    print(f"[HTTP] MJPEG Streamer started on port {port}")
    server.serve_forever()

# --- WMP 受信ロジック ---
def start_stream_rx(port=5005):
    global latest_frame
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # 外部からのUDPを受け入れるため 0.0.0.0
    sock.bind(("0.0.0.0", port))
    
    reassembly_buffer = {}
    print(f"[WMP RX] Stream Receiver waiting on UDP {port}...")

    last_seq = -1  # 最後に処理したフレーム番号

    while True:
        try:
            data, addr = sock.recvfrom(65535) # 最大UDPパケットサイズ
            h = WMPHeader.unpack(data)
            # h[6]:seq, h[7]:f_idx, h[8]:f_total
            seq, f_idx, f_total, payload = h[6], h[7], h[8], data[32:]

            if seq < last_seq:
                continue
                
            if seq > last_seq:
                # 新しいシーケンスが来たら古い未完成バッファを掃除
                keys_to_del = [k for k in reassembly_buffer.keys() if k < seq]
                for k in keys_to_del:
                    del reassembly_buffer[k]
                last_seq = seq

            if seq not in reassembly_buffer:
                reassembly_buffer[seq] = [None] * f_total
            
            reassembly_buffer[seq][f_idx] = payload
            
            # 全フラグメントが揃ったら結合
            if all(chunk is not None for chunk in reassembly_buffer[seq]):
                complete_data = b"".join(reassembly_buffer[seq])
                with frame_lock:
                    latest_frame = complete_data
                del reassembly_buffer[seq]
        except Exception as e:
            print(f"[WMP RX] Error: {e}")

if __name__ == "__main__":
    # ポート番号などは .env から取ることも可能（デフォルト値を設定）
    http_port = int(os.getenv('WMP_HTTP_PORT', 8080))
    udp_port = int(os.getenv('WMP_UDP_PORT', 5005))

    # HTTPサーバーを別スレッドで起動
    http_thread = threading.Thread(target=run_http_server, args=(http_port,), daemon=True)
    http_thread.start()
    
    # メインスレッドでWMP受信を開始
    start_stream_rx(udp_port)