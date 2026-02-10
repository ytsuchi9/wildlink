import adafruit_dht
import board

class WildLinkUnit:
    """温湿度センサー DHT22 ユニット"""
    def __init__(self, config):
        self.val_name = config.get("val_name", "dht22_sensor")
        self.hw_pin = config.get("hw_pin", 18)
        # 物理ピンの設定 (GPIO18等)
        pin = getattr(board, f"D{self.hw_pin}")
        self.sensor = adafruit_dht.DHT22(pin)
        self.log_msg = "Idle"

    def update(self):
        try:
            t = self.sensor.temperature
            h = self.sensor.humidity
            self.log_msg = "Running"
            return {"env_temp": t, "env_hum": h}
        except Exception as e:
            self.log_msg = f"Read Error: {e}"
            return {}