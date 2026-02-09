import subprocess

def get_data(configs):
    try:
        # i2cgetコマンドを使って、バス1、アドレス0x68のレジスタ0x11, 0x12を読み取る
        # -y は確認スキップ、-f は他が使用中でも強制読み込み（UU対策）
        res_msb = subprocess.check_output(["i2cget", "-y", "-f", "1", "0x68", "0x11"])
        res_lsb = subprocess.check_output(["i2cget", "-y", "-f", "1", "0x68", "0x12"])
        
        msb = int(res_msb, 16)
        lsb = int(res_lsb, 16)
        
        # 温度計算（DS3231の仕様）
        temp = msb + ((lsb >> 6) * 0.25)
        
        return True, {"env_temp_rtc": temp}
    except Exception as e:
        return False, {"log_code": 203, "log_msg": str(e)}