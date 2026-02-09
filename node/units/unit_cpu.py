def get_data(configs):
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            cpu_temp = int(f.read()) / 1000.0
        return True, {"sys_cpu_t": cpu_temp}
    except Exception as e:
        return False, {"log_code": 201, "log_msg": str(e)}