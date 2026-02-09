import adafruit_dht
import board

def get_data(configs):
    # 設定からピン番号を取得 (デフォルトは D22)
    pin_num = configs.get("hw_pin", 18)
    pin = getattr(board, f"D{pin_num}")
    
    # センサー初期化
    dht_device = adafruit_dht.DHT22(pin)
    
    try:
        temp = dht_device.temperature
        hum = dht_device.humidity
        
        if temp is not None and hum is not None:
            return True, {
                "env_temp_dht": round(temp, 2),
                "env_hum": round(hum, 2)
            }
        else:
            return False, {"log_code": 204, "log_msg": "DHT22 Reading error"}
            
    except Exception as e:
        # DHT22は読み取り失敗が多いため、エラーにせずリトライを促すのがコツです
        return False, {"log_code": 204, "log_msg": str(e)}
    finally:
        dht_device.exit() # 終了時に通信を解放