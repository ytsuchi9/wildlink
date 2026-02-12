import subprocess
import socket
import time
import sys
import os
import fcntl # 追加：ノンブロッキング制御用

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
    wmp = WMPHeader(node_id="node_001", media_type=2)

    cmd = [
        "ffmpeg", "-y", "-i", "/dev/video0",
        "-vf", "fps=5,scale=320:240",
        "-f", "mjpeg", "-q:v", "10",
        "-tune", "zerolatency", "pipe:1"
    ]

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    
    # 【重要】標準出力を「ノンブロッキングモード」に設定
    # これにより、データがない時にプログラムが止まらず、ある分だけ一気に読めます
    fd = process.stdout.fileno()
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    print(f"[WMP Stream] FFmpeg started. Sending to {dest_ip}:{port}...")

    buffer = b""
    try:
        while True:
            try:
                # パイプから今あるデータを全部読み切る
                while True:
                    chunk = process.stdout.read(8192)
                    if not chunk: break
                    buffer += chunk
                    # バッファが大きくなりすぎたら、古い方を切り捨てる（1MB以上など）
                    if len(buffer) > 1000000:
                        buffer = buffer[-500000:] 
            except BlockingIOError:
                # 読み切ったらここに来る
                pass

            # 最新のフレーム（最後の FF D8 ... FF D9）を探す
            a = buffer.rfind(b'\xff\xd8') # rfind で「最後（最新）」を探すのがコツ！
            b = buffer.find(b'\xff\xd9', a)
            
            if a != -1 and b != -1:
                frame = buffer[a:b+2]
                # 送信
                wmp.send_large_data(sock, (dest_ip, port), frame, flags=1)
                
                # 送信したら、今回使ったフレームより古いデータは全部捨てる
                buffer = buffer[b+2:]
                
                # CPU負荷調整（5fpsなので0.1〜0.2秒待機）
                time.sleep(0.15)
            else:
                # フレームが完成していなければ少し待ってからリトライ
                time.sleep(0.01)

    except KeyboardInterrupt:
        process.terminate()

if __name__ == "__main__":
    TARGET_IP = "192.168.0.102" # Pi 2
    start_stream_tx(TARGET_IP)