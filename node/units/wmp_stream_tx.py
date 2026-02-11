import subprocess
import socket
import time
import sys
import os


# 1. 自分の場所を取得 (wildlink_project/hub)
current_dir = os.path.dirname(os.path.abspath(__file__))
# 2. 親の場所を取得 (node)
node_dir = os.path.dirname(current_dir)
# 3. さらにその親を取得 (wildlink)
wildlink_root = os.path.dirname(node_dir)
# 4. common フォルダのパスを作成 (/opt/wildlink/common)
common_path = os.path.join(wildlink_root, "common")

# パスに追加
sys.path.append(common_path)

# これで common/wmp_core.py が見つかります
import socket
from wmp_core import WMPHeader

print("Success: wmp_core found from common folder!")

def start_stream_tx(dest_ip, port=5005):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    wmp = WMPHeader(node_id="node_001", media_type=2) # Type 2: Video Stream

    # FFmpegコマンド: カメラからMJPEG形式で標準出力(pipe:1)へ吐き出す
    # -g 10: キーフレーム間隔（今回はMJPEGなので各フレーム完結）
    cmd = [
        'ffmpeg', '-f', 'v4l2', '-i', '/dev/video0',
        '-s', '640x480', '-r', '10', '-f', 'mjpeg',
        '-q:v', '5', 'pipe:1'
    ]
    
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    
    print(f"[WMP Stream] FFmpeg started. Sending to {dest_ip}:{port}...")

    buffer = b""
    try:
        while True:
            # MJPEGの区切り(FF D8 ... FF D9)を探して1フレーム分を抽出
            chunk = process.stdout.read(4096)
            if not chunk: break
            buffer += chunk
            
            a = buffer.find(b'\xff\xd8') # JPEG Start
            b = buffer.find(b'\xff\xd9') # JPEG End
            
            if a != -1 and b != -1:
                frame = buffer[a:b+2]
                buffer = buffer[b+2:]
                
                # 土管へ射出！
                # flags=1は「ストリーム中」を意味させる等、仕様に合わせて活用
                wmp.send_large_data(sock, (dest_ip, port), frame, flags=1)
                
    except KeyboardInterrupt:
        process.terminate()

if __name__ == "__main__":
    TARGET_IP = "192.168.0.102" # Pi 2
    start_stream_tx(TARGET_IP)