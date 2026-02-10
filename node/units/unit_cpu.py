import os

class WildLinkUnit:
    """CPU状態監視ユニット"""
    def __init__(self, config):
        self.val_name = config.get("val_name", "cpu_monitor")
        self.log_msg = "Idle"

    def update(self):
        # CPU温度を取得 (Raspberry Pi OS標準のパス)
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp = int(f.read()) / 1000.0
            self.log_msg = "Normal"
            return {"sys_cpu_t": temp}
        except:
            self.log_msg = "Error"
            return {"sys_cpu_t": 0.0}