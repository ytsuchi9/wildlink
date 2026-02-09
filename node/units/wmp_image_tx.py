import socket
import os
from wmp_core import WMPHeader

def start_image_tx(dest_ip, image_path, port=5005):
    if not os.path.exists(image_path):
        print(f"Error: {image_path} not found.")
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    wmp = WMPHeader(node_id="node_001", media_type=3) # Type 3: Image

    with open(image_path, "rb") as f:
        img_data = f.read()

    print(f"[WMP TX] Sending {image_path} ({len(img_data)} bytes)...")
    
    # 分割送信メソッドの呼び出し
    wmp.send_large_data(sock, (dest_ip, port), img_data, flags=1)
    
    print("Done.")

if __name__ == "__main__":
    TARGET_IP = "192.168.0.102" # Pi 2のIP
    IMAGE_FILE = "test.jpg"      # 送信したい画像ファイル名
    start_image_tx(TARGET_IP, IMAGE_FILE)