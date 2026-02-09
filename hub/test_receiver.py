import socket
from wmp_core import WMPHeader

def start_test_rx(port=5005):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    print(f"[WMP RX] Listening on port {port}...")

    while True:
        data, addr = sock.recvfrom(2048) # ヘッダー(32) + ペイロード
        header_bin = data[:32]
        h = WMPHeader.unpack(header_bin)
        
        # 表示 (h[1]が文字列になっています)
        # h[1]: node_id, h[2]: media_type, h[4]: flags, h[5]: p_len, h[6]: seq, h[7]: f_idx, h[8]: f_tot
        print(f"--- WMP Packet Received ---")
        print(f"From: {h[1]}, Type: {h[2]}, Seq: {h[6]}")
        print(f"Flags: {h[4]}, Payload: {h[5]} bytes, Frag: {h[7]}/{h[8]}")
        if h[5] > 0:
            print(f"Data: {data[32:].decode(errors='ignore')}")

if __name__ == "__main__":
    start_test_rx()