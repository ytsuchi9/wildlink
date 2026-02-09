import socket
import time
from wmp_core import WMPHeader

def start_test_tx(dest_ip, port=5005):
    # 1. 土管（UDPソケット）の準備
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # 2. ヘッダー生成器の初期化 (node_001, Video型, UDP)
    wmp = WMPHeader(node_id="node_001", media_type=1, bus_type=1)
    
    print(f"[WMP TX] Sending test packets to {dest_ip}:{port}...")

    # 3. テストパケットを3回送ってみる
    for i in range(3):
        msg = f"WMP Test Message #{i+1}".encode()
        
        # ヘッダーをパック (Startフラグは1回目だけ立てる例)
        flags = 1 if i == 0 else 0
        header = wmp.pack(flags=flags, p_len=len(msg), seq=i)
        
        # 土管へ射出！ (ヘッダー32byte + ペイロード)
        sock.sendto(header + msg, (dest_ip, port))
        
        print(f"Sent Packet {i+1}")
        time.sleep(1)

    # 4. 終了パケットを送信 (Endフラグ=2)
    end_header = wmp.pack(flags=2, p_len=0, seq=3)
    sock.sendto(end_header, (dest_ip, port))
    print("Sent End Packet.")

if __name__ == "__main__":
    # Pi 2のIPアドレスを指定してください
    TARGET_IP = "192.168.0.102" 
    start_test_tx(TARGET_IP)