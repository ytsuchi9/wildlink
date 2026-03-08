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
    """MJPEGストリームを生成（パケット途絶で自動切断し、ブラウザにリロードを促す）"""
    print(f"🎬 [WMP RX] Client connected to port {port}")
    last_frame_hash = None
    last_packet_time = time.time() # 💡 最後にパケットを受け取った時刻
    
    try:
        while True:
            frame = frame_buffers.get(port)
            current_time = time.time()

            if frame:
                current_hash = hash(frame)
                if current_hash != last_frame_hash:
                    # 💡 新しいフレームが来たので、時刻を更新
                    last_frame_hash = current_hash
                    last_packet_time = current_time 
                    
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            
            # 💡 対策：3秒間パケットが届かなければ、ストリームを強制終了する
            # これにより、ブラウザ側で「画像が壊れた」または「接続が切れた」と認識させます
            if current_time - last_packet_time > 3.0:
                print(f"⚠️ [WMP RX] Timeout on port {port}. Closing stream to client.")
                break # ループを抜けて Response を終了させる

            time.sleep(0.05) 
            
    except (GeneratorExit, Exception) as e:
        print(f"🛑 [WMP RX] Client connection error on {port}: {e}")
    finally:
        if port in frame_buffers:
            frame_buffers[port] = None

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