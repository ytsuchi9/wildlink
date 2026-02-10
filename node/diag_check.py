import sys
import os
import importlib

# 診断対象のリスト
UNITS = [
    'wmp_core',
    'units.unit_camera_v1',
    'utils.mqtt_client' # もしあれば
]

def diagnostic():
    print("=== WildLink Node Diagnostic Boot ===")
    print(f"Current Directory: {os.getcwd()}")
    
    # nodeフォルダをパスに追加 (これが必要なはず)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if base_dir not in sys.path:
        sys.path.append(base_dir)
        print(f"Added to sys.path: {base_dir}")

    for unit in UNITS:
        try:
            importlib.import_module(unit)
            print(f"[ OK ] {unit} loaded successfully.")
        except Exception as e:
            print(f"[FAIL] {unit} failed to load.")
            print(f"       Error: {e}")

    print("======================================")

if __name__ == "__main__":
    diagnostic()