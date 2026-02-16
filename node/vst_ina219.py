# /opt/wildlink/node/vst_ina219.py
from ina219 import INA219, DeviceRangeError
from vst_base import WildLinkVSTBase

class VSTIna219(WildLinkVSTBase):
    def __init__(self, config):
        super().__init__(config)
        # シャント抵抗値などもDBから変えられるように
        shunt = config.get("val_res", 0.1) 
        self.ina = INA219(shunt_ohms=shunt)
        self.ina.configure()

    def update(self, cmd_dict=None):
        try:
            v = self.ina.voltage()
            i = self.ina.current()
            return {
                "sys_volt": round(v, 2),
                "sys_curr": round(i, 2),
                "sys_watt": round((v * i) / 1000.0, 3),
                "log_msg": "Power OK"
            }
        except DeviceRangeError:
            return {"log_msg": "Range Error"}
        except Exception as e:
            return {"log_msg": str(e)}