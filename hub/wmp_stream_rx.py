import socket
from wmp_core import WMPHeader

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

        # フレーム完成！
        if all(chunk is not None for chunk in reassembly_buffer[seq]):
            complete_data = b"".join(reassembly_buffer[seq])
            
            # /dev/shm (共有メモリ) に保存してWebサーバー等から参照可能にする
            with open("/dev/shm/latest.jpg", "wb") as f:
                f.write(complete_data)
            
            print(f"Frame {seq} displayed. (Size: {len(complete_data)} bytes)")
            last_complete_seq = seq
            del reassembly_buffer[seq]

if __name__ == "__main__":
    start_stream_rx()