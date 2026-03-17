import struct
import time

class WMPHeader:
    MAGIC = b"WMP!"
    FORMAT_STRICT = "!4s12sIIIHH" # 合計 32 bytes
    MTU_LIMIT = 1400

    def __init__(self, node_id, media_type=1, bus_type=1):
        """
        node_id: これが sys_id (例: "node_001") に相当する
        """
        # 💡 変数名は node_id_bin のままでも良いですが、意味は sys_id です
        self.node_id_bin = node_id.encode().ljust(12, b'\0')
        self.media_type = media_type
        self.bus_type = bus_type
        self.seq_num = 0

    def pack(self, flags=0, p_len=0, seq=0, f_idx=0, f_total=1):
        combined_info = (self.media_type << 24) | (self.bus_type << 16) | (flags & 0xFFFF)
        return struct.pack(self.FORMAT_STRICT, self.MAGIC, self.node_id_bin, 
                          combined_info, p_len, seq, f_idx, f_total)

    @classmethod
    def unpack(cls, data):
        if len(data) < 32:
            raise ValueError("Data too short to be a WMP packet")
            
        header_data = data[:32]
        vals = struct.unpack(cls.FORMAT_STRICT, header_data)
        
        magic = vals[0]
        # 💡 ここで取り出した node_id が sys_id として使われる
        sys_id = vals[1].decode().strip(chr(0))
        info = vals[2]
        
        media_type = info >> 24
        bus_type = (info >> 16) & 0xFF
        flags = info & 0xFFFF
        p_len = vals[3]
        seq = vals[4]
        f_idx = vals[5]
        f_total = vals[6]
        
        return (magic, sys_id, media_type, bus_type, flags, p_len, seq, f_idx, f_total)

    def send_large_data(self, sock, dest_addr, data, flags=0):
        total_len = len(data)
        f_total = (total_len + self.MTU_LIMIT - 1) // self.MTU_LIMIT
        
        for i in range(f_total):
            start = i * self.MTU_LIMIT
            end = min(start + self.MTU_LIMIT, total_len)
            chunk = data[start:end]
            
            header = self.pack(flags=flags, p_len=len(chunk), 
                               seq=self.seq_num, f_idx=i, f_total=f_total)
            sock.sendto(header + chunk, dest_addr)
            time.sleep(0.001) 

        self.seq_num += 1