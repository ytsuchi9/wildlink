# /opt/wildlink/node/vst_rtc.py
import smbus2
from vst_base import WildLinkVSTBase

class VSTRtc(WildLinkVSTBase):
    def __init__(self, config):
        super().__init__(config)
        self.hw_addr = config.get("hw_addr", 0x68)
        try:
            self.bus = smbus2.SMBus(1)
        except Exception as e:
            self.log_msg = f"Bus Error: {e}"

    def update(self, cmd_dict=None):
        try:
            # DS3231のレジスタから温度を取得
            msb = self.bus.read_byte_data(self.hw_addr, 0x11)
            lsb = self.bus.read_byte_data(self.hw_addr, 0x12)
            temp = msb + ((lsb >> 6) * 0.25)
            
            return {
                "env_temp": temp,  # 他のセンサーと合わせて env_temp に統一
                "log_msg": "RTC Temp OK",
                "val_status": "synced"
            }
        except Exception as e:
            return {"log_msg": f"Read Error: {e}"}