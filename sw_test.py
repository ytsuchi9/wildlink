import RPi.GPIO as GPIO
import time

PIN = 17

GPIO.setmode(GPIO.BCM)
# プルアップ設定
GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print(f"--- GPIO {PIN} Test Start (Ctrl+C to stop) ---")
print("Status: HIGH=Not Pressed, LOW=Pressed")

try:
    while True:
        status = GPIO.input(PIN)
        if status == GPIO.LOW:
            print("🔘 Button Pressed! (LOW)")
        else:
            # 垂れ流すと見づらいので、変化がない時はドットを出す
            print(".", end="", flush=True)
        time.sleep(0.2)
except KeyboardInterrupt:
    print("\nTest Stopped.")
finally:
    GPIO.cleanup()