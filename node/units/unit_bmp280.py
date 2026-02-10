import smbus2
import bme280

class WildLinkUnit:
    def __init__(self, config):
        self.val_name = config.get("val_name", "bmp280_sensor")
        self.hw_addr = config.get("hw_addr", 0x76)
        self.bus = smbus2.SMBus(1)
        # 以前のロジック通り、初期化パラメータをロード
        try:
            self.calib = bme280.load_calibration_params(self.bus, self.hw_addr)
            self.log_msg = "Idle"
        except Exception as e:
            self.log_msg = f"Init Error: {e}"

    def update(self):
        try:
            # 以前のロジックでサンプリング
            d = bme280.sample(self.bus, self.hw_addr, self.calib)
            return {
                "env_temp": round(d.temperature, 2),
                "env_pres": round(d.pressure, 2)
            }
        except Exception as e:
            self.log_msg = f"Read Error: {e}"
            return {}