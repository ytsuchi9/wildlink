import sys
import os

# 1. 自分の場所を取得 (wildlink_project/hub)
current_dir = os.path.dirname(os.path.abspath(__file__))
# 2. 親の場所を取得 (wildlink_project)
parent_dir = os.path.dirname(current_dir)
# 3. common フォルダのパスを作成 (wildlink_project/common)
common_path = os.path.join(parent_dir, "common")

# パスに追加
sys.path.append(common_path)

# これで common/wmp_core.py が見つかります
import socket
from wmp_core import WMPHeader

print("Success: wmp_core found from common folder!")

def start_stream_rx(port=5005):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    
    reassembly_buffer = {}
    last_complete_seq = -1

    print(f"[WMP RX] Stream Receiver waiting on port {port}...")

    while True:
        data, addr = sock.recvfrom(2048)
        h = WMPHeader.unpack(data)
        node_id, seq, f_idx, f_total, payload = h[1], h[6], h[7], h[8], data[32:]

        # 古いSeq（あきらめたはずのもの）が届いたら無視
        if seq < last_complete_seq: continue

        if seq not in reassembly_buffer:
            reassembly_buffer[seq] = [None] * f_total
            # メモリ節約：古いバッファを掃除（あきらめ）
            if len(reassembly_buffer) > 5:
                oldest_seq = min(reassembly_buffer.keys())
                del reassembly_buffer[oldest_seq]
        
        reassembly_buffer[seq][f_idx] = payload

        # 全てのパーツが揃ったかチェック
        if all(chunk is not None for chunk in reassembly_buffer[seq]):
            print(f"--- Seq:{seq} Complete! ---")
            complete_data = b"".join(reassembly_buffer[seq])
            
            # 【ここを修正！】
            # 特定の名前で保存するのではなく、常に「最新の1枚」として保存
            save_path = "/dev/shm/latest.jpg"
            try:
                with open(save_path, "wb") as f:
                    f.write(complete_data)
                print(f"Successfully updated: {save_path}")
            except Exception as e:
                print(f"File Save Error: {e}")
            
            # メモリ解放
            del reassembly_buffer[seq]

if __name__ == "__main__":
    start_stream_rx()