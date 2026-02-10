from ina219 import INA219
from ina219 import DeviceRangeError

class WildLinkUnit:
    def __init__(self, config):
        self.val_name = config.get("val_name", "power_monitor")
        # addr引数ではなく、内部のアドレス（通常0x40）で初期化
        self.ina = INA219(shunt_ohms=0.1)
        self.ina.configure()
        self.log_msg = "Idle"

    def update(self):
        try:
            v = self.ina.voltage()
            i = self.ina.current()
            p = (v * i) / 1000.0 # 電力計算
            return {
                "sys_volt": round(v, 2),
                "sys_curr": round(i, 2),
                "sys_watt": round(p, 3)
            }
        except DeviceRangeError:
            return {"log_msg": "Power Range Error"}
        except:
            return {}