# /opt/wildlink/node/vst_bmp280.py
import smbus2
import bme280
from vst_base import WildLinkVSTBase

class VSTBmp280(WildLinkVSTBase):
    def __init__(self, config):
        super().__init__(config)
        self.hw_addr = config.get("hw_addr", 0x76) # DBから取得
        try:
            self.bus = smbus2.SMBus(1)
            self.calib = bme280.load_calibration_params(self.bus, self.hw_addr)
        except Exception as e:
            self.log_msg = f"Init Error: {e}"

    def update(self, cmd_dict=None):
        try:
            d = bme280.sample(self.bus, self.hw_addr, self.calib)
            return {
                "env_temp": round(d.temperature, 2),
                "env_pres": round(d.pressure, 2),
                "log_msg": "OK"
            }
        except Exception as e:
            return {"log_msg": f"Read Error: {e}"}
