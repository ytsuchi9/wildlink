from ina219 import INA219
from ina219 import DeviceRangeError

def get_data(configs):
    SHUNT_OHMS = 0.1 # 標準的なモジュールは通常0.1Ω
    ina = INA219(SHUNT_OHMS, address=0x40)
    ina.configure()

    try:
        volt = ina.voltage()      # バス電圧(V)
        amp = ina.current()       # 電流(mA)
        power = ina.power()       # 電力(mW)
        
        return True, {
            "sys_volt": round(volt, 2),
            "sys_amp": round(amp, 2),
            "sys_watt": round(power / 1000.0, 3) # Wに変換
        }
    except DeviceRangeError as e:
        return False, {"log_code": 205, "log_msg": "INA219 Range Error"}
    except Exception as e:
        return False, {"log_code": 205, "log_msg": str(e)}