import socket
from wmp_core import WMPHeader

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
            print(f"--- Seq:{seq} Complete! Writing file... ---")
            complete_data = b"".join(reassembly_buffer[seq])
            
            # 届いたデータを画像として保存
            with open(f"received_{node_id}_{seq}.jpg", "wb") as f:
                f.write(complete_data)
            
            # メモリ解放
            del reassembly_buffer[seq]

if __name__ == "__main__":
    start_image_rx()