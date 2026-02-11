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

print("✅ Success: wmp_core found from common folder!")

def start_image_rx(port=5005):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    
    # データを貯めるバッファ {seq_num: [chunk0, chunk1, ...]}
    reassembly_buffer = {}

    print(f"[WMP RX] Image Receiver waiting on port {port}...")

    while True:
        data, addr = sock.recvfrom(2048)
        h = WMPHeader.unpack(data)
        
        # ヘッダー情報の抽出
        node_id, seq, f_idx, f_total, payload = h[1], h[6], h[7], h[8], data[32:]

        # バッファに初期化/追加
        if seq not in reassembly_buffer:
            reassembly_buffer[seq] = [None] * f_total
        
        reassembly_buffer[seq][f_idx] = payload
        print(f"Received Seq:{seq} Frag:{f_idx+1}/{f_total}")
        
        # wmp_image_rx.py の all(...) の前にこれを入れてみてください
        missing_count = reassembly_buffer[seq].count(None)
        if f_idx % 100 == 0: # 100個ごとに進捗を表示
            print(f"Seq:{seq} Progress: {f_total - missing_count}/{f_total}")
        
        if missing_count == 0:
            print("--- Success! All fragments arrived. ---")
        # ... 以下書き出し処理 ...                
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
    start_image_rx()