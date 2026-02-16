import os
import subprocess
# /opt/wildlink/node/vst_sys_monitor.py
from vst_base import WildLinkVSTBase # クラス名を正解に合わせる

class VSTSysMonitor(WildLinkVSTBase): # 継承元を修正
    def __init__(self, params):
        super().__init__(params) # 親クラスの初期化を呼ぶ
        # 親クラス(WildLinkVSTBase)が self.val_name 等をセットしてくれます
        self.val_name = params.get("val_name", "SysMonitor")

    def get_cpu_temp(self):
        """CPU温度を取得"""
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp = int(f.read()) / 1000.0
            return temp
        except:
            return 0.0

    def get_net_rssi(self):
        """WiFiのRSSI(信号強度)を取得"""
        try:
            cmd = "iwconfig wlan0 | grep 'Link Quality'"
            res = subprocess.check_output(cmd, shell=True).decode()
            # "Link Quality=70/70  Signal level=-30 dBm" から抽出
            if "Signal level=" in res:
                rssi = int(res.split("Signal level=")[1].split(" ")[0])
                return rssi
        except:
            return 0
        return 0

    def update(self, cmd_dict=None):
        # 命名規則: sys_ (状態), net_ (通信)
        report = {
            "sys_cpu_t": self.get_cpu_temp(),
            "net_rssi": self.get_net_rssi(),
            "log_msg": "System healthy"
        }
        return report