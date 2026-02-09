import socket
import os
import sys
# 共通ライブラリを読み込むためのパス設定
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from wmp_core import WMPHeader

def start_hub_rx(port=5005):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    
    reassembly_buffer = {}
    last_complete_seq = -1

    print(f"[*] WMP Hub Receiver waiting on port {port}...")

    while True:
        try:
            data, addr = sock.recvfrom(65535) # 最大サイズで待機
            h = WMPHeader.unpack(data)
            # node_id:h[1], flags:h[4], seq:h[6], f_idx:h[7], f_total:h[8]
            flags, seq, f_idx, f_total = h[4], h[6], h[7], h[8]
            payload = data[32:]

            # --- [重要] セッション管理: Flags=1 (Start/New Frame) ならリセット ---
            if flags == 1 and f_idx == 0:
                if seq < last_complete_seq: # 送信側が再起動したと判断
                    print(f"[WMP RX] New session detected (Seq:{seq}). Resetting buffer.")
                    reassembly_buffer.clear()
                    last_complete_seq = -1

            # 古いSeq（あきらめたはずのもの）が届いたら無視
            if seq < last_complete_seq:
                continue

            if seq not in reassembly_buffer:
                reassembly_buffer[seq] = [None] * f_total
            
            reassembly_buffer[seq][f_idx] = payload

            # フレームが揃ったか確認
            if all(chunk is not None for chunk in reassembly_buffer[seq]):
                complete_data = b"".join(reassembly_buffer[seq])
                
                # /dev/shm (共有メモリ) に保存
                # ブラウザはこのファイルを 0.1秒おきに読みに行く
                with open("/dev/shm/latest.jpg", "wb") as f:
                    f.write(complete_data)
                
                last_complete_seq = seq
                del reassembly_buffer[seq]
                
                # メモリ管理：溜まりすぎたバッファを掃除
                if len(reassembly_buffer) > 10:
                    oldest_seq = min(reassembly_buffer.keys())
                    del reassembly_buffer[oldest_seq]

        except Exception as e:
            print(f"Receive Error: {e}")

if __name__ == "__main__":
    start_hub_rx()