import sys
import os
import socket
import threading
import time
from flask import Flask, Response, request

# --- パス解決 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
wildlink_root = os.path.dirname(current_dir)
common_path = os.path.join(wildlink_root, "common")
if common_path not in sys.path:
    sys.path.append(common_path)

from wmp_core import WMPHeader

app = Flask(__name__)

# データ保持用
frame_buffers = {}       # { port: jpeg_bytes }
assembly_buffers = {}    # { port: [chunk1, chunk2, ...] }

def udp_receiver(port):
    """UDPパケットを受信し、JPEGフレームを再構築する"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    # ソケット受信バッファを拡大（PiZeroからの高速連打に対応）
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
    print(f"📡 [WMP RX] Listening on UDP port {port}")
    
    while True:
        try:
            data, addr = sock.recvfrom(2048)
            # WMPヘッダーの解析 (unpack結果: 0:magic, 1:node_id, ..., 5:p_len, 7:f_idx, 8:f_total)
            res = WMPHeader.unpack(data)
            p_len = res[5]
            f_idx = res[7]
            f_total = res[8]
            payload = data[32:32+p_len]

            if f_total == 1:
                frame_buffers[port] = payload
            else:
                # 新しいフレーム(idx=0)が来たらバッファをリセット
                if f_idx == 0:
                    assembly_buffers[port] = [None] * f_total
                
                if port in assembly_buffers:
                    assembly_buffers[port][f_idx] = payload
                    
                    # 全て揃ったら結合
                    if all(v is not None for v in assembly_buffers[port]):
                        frame_buffers[port] = b"".join(assembly_buffers[port])
                        assembly_buffers[port] = [] # クリア
        except Exception:
            pass

def generate_mjpeg(port):
    """MJPEGストリームを生成"""
    last_frame_hash = None
    while True:
        frame = frame_buffers.get(port)
        if frame:
            current_hash = hash(frame)
            if current_hash != last_frame_hash:
                last_frame_hash = current_hash
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        
        # FPSに合わせて待機 (15fps程度なら0.03s程度)
        time.sleep(0.04)

@app.route('/stream/<target>')
def stream(target):
    # 新しい命名規則に合わせたマッピング
    mapping = {
        "cam_main": 5005,
        "cam_sub":  5006,
        "cam_rear": 5007,
        "pi": 5005,  # 互換性のために残す
        "usb": 5006  # 互換性のために残す
    }
    port = mapping.get(target)
    if not port:
        return "Unknown target", 404
    
    return Response(generate_mjpeg(port),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # 将来的に cam_rear 等が増えても良いように範囲を広げておく
    listen_ports = [5005, 5006, 5007, 5008]
    
    for p in listen_ports:
        t = threading.Thread(target=udp_receiver, args=(p,), daemon=True)
        t.start()
        
    print(f"🚀 [HTTP] WildLink MJPEG Bridge started on port 8080")
    app.run(host='0.0.0.0', port=8080, threaded=True, debug=False)