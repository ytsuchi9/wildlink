import RPi.GPIO as GPIO
import os
import time

def start_monitoring(configs):
    pin = configs.get("hw_pin", 26)
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    print(f"[unit_sw_monitor] Polling mode started on GPIO{pin}")
    
    while True:
        # ボタンが押されているか直接監視 (Lで押下)
        if GPIO.input(pin) == GPIO.LOW:
            press_start = time.time()
            # 押されている間ループ
            while GPIO.input(pin) == GPIO.LOW:
                if time.time() - press_start > 3:
                    print("!!! SHUTDOWN BUTTON DETECTED !!!")
                    os.system("sudo shutdown -h now")
                    return
                time.sleep(0.1)
        time.sleep(0.5) # 0.5秒おきにチェック（CPU負荷低減）

def get_data(configs):
    return True, {}