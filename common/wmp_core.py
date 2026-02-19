import struct
import time

class WMPHeader:
    MAGIC = b"WMP!"
    FORMAT_STRICT = "!4s12sIIIHH" # 合計 32 bytes
    MTU_LIMIT = 1400  # UDPで安全に送れる最大ペイロードサイズ

    def __init__(self, node_id, media_type=1, bus_type=1):
        """
        初期化: 自分のノードIDやメディアタイプを設定
        media_type: 1=Photo, 2=Video, 3=Audio
        """
        self.node_id_bin = node_id.encode().ljust(12, b'\0')
        self.media_type = media_type
        self.bus_type = bus_type
        self.seq_num = 0

    def pack(self, flags=0, p_len=0, seq=0, f_idx=0, f_total=1):
        """ヘッダーをバイナリにパックする"""
        combined_info = (self.media_type << 24) | (self.bus_type << 16) | (flags & 0xFFFF)
        return struct.pack(self.FORMAT_STRICT, self.MAGIC, self.node_id_bin, 
                          combined_info, p_len, seq, f_idx, f_total)

    @classmethod
    def unpack(cls, data):
        """
        バイナリデータを解析して各フィールドを返す (受信側で使用)
        """
        if len(data) < 32:
            raise ValueError("Data too short to be a WMP packet")
            
        header_data = data[:32]
        vals = struct.unpack(cls.FORMAT_STRICT, header_data)
        
        magic = vals[0]
        node_id = vals[1].decode().strip(chr(0))
        info = vals[2]
        
        media_type = info >> 24
        bus_type = (info >> 16) & 0xFF
        flags = info & 0xFFFF
        p_len = vals[3]
        seq = vals[4]
        f_idx = vals[5]
        f_total = vals[6]
        
        return (magic, node_id, media_type, bus_type, flags, p_len, seq, f_idx, f_total)

    def send_large_data(self, sock, dest_addr, data, flags=0):
        """
        大きなデータ（JPEGフレーム等）を自動分割してUDPで送信する。
        これが「土管」のパケット配送エンジンになります。
        """
        total_len = len(data)
        # 何分割するか計算
        f_total = (total_len + self.MTU_LIMIT - 1) // self.MTU_LIMIT
        
        for i in range(f_total):
            start = i * self.MTU_LIMIT
            end = min(start + self.MTU_LIMIT, total_len)
            chunk = data[start:end]
            
            # ヘッダー作成 (f_idx: 何番目の欠片か, f_total: 全部で何枚か)
            header = self.pack(flags=flags, p_len=len(chunk), 
                               seq=self.seq_num, f_idx=i, f_total=f_total)
            
            # UDP送信
            sock.sendto(header + chunk, dest_addr)
            
            # 連続送信によるバッファ溢れを防ぐため、ごく微小な隙間を作る
            # ネットワークの安定性に合わせて調整（0.001〜0.01）
            time.sleep(0.005) 
            
        self.seq_num += 1 # 次のフレームへ