import os
import smbus2
import bme280  # pip3 install RPi.bme280 でインストール可能

def get_data(configs):
    try:
        # --- 1. CPU温度 (sys_cpu_t) ---
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            cpu_temp = int(f.read()) / 1000.0

        # --- 2. BMP280 (env_temp, env_pres) ---
        # I2Cの設定
        port = 1
        address = 0x76  # さきほど確認したアドレス
        bus = smbus2.SMBus(port)
        calibration_params = bme280.load_calibration_params(bus, address)
        
        # 測定
        data = bme280.sample(bus, address, calibration_params)
        
        # --- 3. データのパッキング ---
        payload = {
            "sys_cpu_t": cpu_temp,
            "env_temp": round(data.temperature, 2),
            "env_pres": round(data.pressure, 2),
            "env_hum": round(data.humidity, 2)  # BMP280なら0、BMEなら湿度が入る
        }

        return True, payload

    except Exception as e:
        return False, {"log_code": 202, "log_msg": str(e)}

if __name__ == "__main__":
    # 単体テスト用
    print(get_data({}))