import smbus2
import bme280

def get_data(configs):
    try:
        bus = smbus2.SMBus(1)
        address = configs.get("hw_addr", 0x76) # configからアドレス取得
        calib = bme280.load_calibration_params(bus, address)
        d = bme280.sample(bus, address, calib)
        return True, {
            "env_temp": round(d.temperature, 2),
            "env_pres": round(d.pressure, 2)
        }
    except Exception as e:
        return False, {"log_code": 202, "log_msg": str(e)}