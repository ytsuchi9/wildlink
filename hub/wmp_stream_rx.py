import socket
import sys
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO

# --- パス解決 (2段遡って common を追加) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
common_path = os.path.join(parent_dir, "common")
sys.path.append(common_path)

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
                print(f"Client disconnected: {e}")
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
    sock.bind(("0.0.0.0", port))
    
    reassembly_buffer = {}
    print(f"[WMP RX] Stream Receiver waiting on UDP {port}...")

    last_seq = -1  # 最後に処理したフレーム番号

    while True:
        data, addr = sock.recvfrom(4096)
        h = WMPHeader.unpack(data)
        seq, f_idx, f_total, payload = h[6], h[7], h[8], data[32:]

        # 【改善】古いフレームのパケットは無視する
        if seq < last_seq:
            continue
            
        # 【改善】新しいフレームが来たら、それより古い仕掛かりバッファを捨てる
        if seq > last_seq:
            # 未完成の古いバッファを一掃
            keys_to_del = [k for k in reassembly_buffer.keys() if k < seq]
            for k in keys_to_del:
                del reassembly_buffer[k]
            last_seq = seq

        if seq not in reassembly_buffer:
            reassembly_buffer[seq] = [None] * f_total
        
        reassembly_buffer[seq][f_idx] = payload
        
        if all(chunk is not None for chunk in reassembly_buffer[seq]):
            complete_data = b"".join(reassembly_buffer[seq])
            with frame_lock:
                latest_frame = complete_data
            del reassembly_buffer[seq]

if __name__ == "__main__":
    # HTTPサーバーを別スレッドで起動
    http_thread = threading.Thread(target=run_http_server, args=(8080,), daemon=True)
    http_thread.start()
    
    # メインスレッドでWMP受信を開始
    start_stream_rx()