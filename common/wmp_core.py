import struct
import time

class WMPHeader:
    MAGIC = b"WMP!"
    FORMAT_STRICT = "!4s12sIIIHH" # 32 bytes
    MTU_LIMIT = 1400  # UDPで安全に送れる最大ペイロードサイズ

    def __init__(self, node_id, media_type=1, bus_type=1):
        self.node_id_bin = node_id.encode().ljust(12, b'\0')
        self.media_type = media_type
        self.bus_type = bus_type
        self.seq_num = 0

    def pack(self, flags=0, p_len=0, seq=0, f_idx=0, f_total=1):
        combined_info = (self.media_type << 24) | (self.bus_type << 16) | (flags & 0xFFFF)
        return struct.pack(self.FORMAT_STRICT, self.MAGIC, self.node_id_bin, 
                          combined_info, p_len, seq, f_idx, f_total)

    def send_large_data(self, sock, dest_addr, data, flags=0):
        """
        大きなデータを自動分割してUDPで送信する
        """
        total_len = len(data)
        # 何分割するか計算
        f_total = (total_len + self.MTU_LIMIT - 1) // self.MTU_LIMIT
        
        for i in range(f_total):
            start = i * self.MTU_LIMIT
            end = min(start + self.MTU_LIMIT, total_len)
            chunk = data[start:end]
            
            # ヘッダー作成 (flagsは最初のパケットに適用、または任意)
            header = self.pack(flags=flags, p_len=len(chunk), 
                               seq=self.seq_num, f_idx=i, f_total=f_total)
            
            sock.sendto(header + chunk, dest_addr)
            # 案B(QoS): 連続送信によるバッファ溢れを防ぐため、ごく微小な隙間を作る
            #time.sleep(0.001)
            #time.sleep(0.005)
            time.sleep(0.01) 
            
        self.seq_num += 1 # 1つの大きなデータ(フレーム)単位でSeqを回す

    @classmethod
    def unpack(cls, data):
        header_data = data[:32]
        vals = struct.unpack(cls.FORMAT_STRICT, header_data)
        info = vals[2]
        return (vals[0], vals[1].decode().strip(chr(0)), info >> 24, (info >> 16) & 0xFF, 
                info & 0xFFFF, vals[3], vals[4], vals[5], vals[6])