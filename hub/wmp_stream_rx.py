import sys
import os
import socket
import threading
from flask import Flask, Response, request

# --- パス解決ロジック ---
current_dir = os.path.dirname(os.path.abspath(__file__)) # /opt/wildlink/hub
wildlink_root = os.path.dirname(current_dir)             # /opt/wildlink
common_path = os.path.join(wildlink_root, "common")

if common_path not in sys.path:
    sys.path.append(common_path)

try:
    from wmp_core import WMPHeader
    print("✔ Success: wmp_core found from common folder!")
except ImportError:
    print(f"✘ Error: Could not find wmp_core in {common_path}")
    sys.exit(1)

app = Flask(__name__)

# ポートごとの最新フレームを保持する辞書
# { 5005: b'jpeg_data...', 5006: b'jpeg_data...' }
frame_buffers = {}
# パケットの欠片を組み立てるためのテンポラリバッファ
assembly_buffers = {}

def udp_receiver(port):
    """特定のポートでUDPを待ち受け、WMPパケットを組み立てるスレッド"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    print(f"[WMP RX] Thread started for UDP port {port}")
    
    while True:
        data, addr = sock.recvfrom(2048)
        try:
            # WMPヘッダーの解析
            res = WMPHeader.unpack(data)
            p_len = res[5]
            f_idx = res[7]
            f_total = res[8]
            payload = data[32:32+p_len]

            if f_total == 1:
                # 分割なしならそのままバッファへ
                frame_buffers[port] = payload
            else:
                # 分割パケットの組み立て
                if f_idx == 0:
                    assembly_buffers[port] = [None] * f_total
                
                if port in assembly_buffers:
                    assembly_buffers[port][f_idx] = payload
                    
                    # 全ての欠片が揃ったか確認
                    if all(assembly_buffers[port]):
                        frame_buffers[port] = b"".join(assembly_buffers[port])
                        del assembly_buffers[port]
        except Exception as e:
            # print(f"[WMP RX] Port {port} error: {e}")
            pass

def generate_mjpeg(port):
    last_frame = None
    while True:
        # そのポートに新しいフレームがあるかチェック
        frame = frame_buffers.get(port)
        if frame and frame != last_frame:
            last_frame = frame
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            import time
            time.sleep(0.05) # フレーム更新待ち

@app.route('/stream/<target>')
def stream(target):
    """
    URLに応じたストリームを返す
    例: /stream/pi -> 5005, /stream/usb -> 5006
    """
    mapping = {
        "pi": 5005,
        "usb": 5006,
        "cam1": 5007,
        "cam2": 5008
    }
    port = mapping.get(target)
    if not port:
        return "Unknown target", 404
    
    return Response(generate_mjpeg(port),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # 待ち受けるポートのリスト
    listen_ports = [5005, 5006, 5007, 5008]
    
    # 各ポートに対して受信用スレッドを起動
    for p in listen_ports:
        t = threading.Thread(target=udp_receiver, args=(p,), daemon=True)
        t.start()
        
    print(f"[HTTP] Multi-streamer started on port 8080")
    print(f" - http://<Pi2_IP>:8080/stream/pi  (Port 5005)")
    print(f" - http://<Pi2_IP>:8080/stream/usb (Port 5006)")
    
    app.run(host='0.0.0.0', port=8080, threaded=True)