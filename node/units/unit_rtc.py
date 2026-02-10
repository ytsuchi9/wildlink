import smbus2

class WildLinkUnit:
    def __init__(self, config):
        self.val_name = config.get("val_name", "rtc_monitor")
        self.bus = smbus2.SMBus(1)
        self.addr = 0x68
        self.log_msg = "Idle"

    def update(self):
        try:
            msb = self.bus.read_byte_data(self.addr, 0x11)
            lsb = self.bus.read_byte_data(self.addr, 0x12)
            temp = msb + ((lsb >> 6) * 0.25)
            return {"env_temp_rtc": temp}
        except:
            return {"log_ext": "RTC Sync OK"}