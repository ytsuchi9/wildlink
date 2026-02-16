# /opt/wildlink/node/vst_dht22.py
import adafruit_dht
import board
from vst_base import WildLinkVSTBase

class VSTDht22(WildLinkVSTBase):
    def __init__(self, config):
        super().__init__(config)
        self.hw_pin = config.get("hw_pin", 18) # DBから取得
        pin = getattr(board, f"D{self.hw_pin}")
        self.sensor = adafruit_dht.DHT22(pin)

    def update(self, cmd_dict=None):
        try:
            return {
                "env_temp": self.sensor.temperature,
                "env_hum": self.sensor.humidity,
                "log_msg": "OK"
            }
        except Exception as e:
            return {"log_msg": f"Read Error: {e}"}