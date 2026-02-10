import sys
import os
import importlib

def diagnostic():
    print("=== WildLink Node Diagnostic Boot ===")
    print(f"Current Directory: {os.getcwd()}")
    
    # 実行ファイルの絶対パスを取得
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 【重要】マウント状況に依存しないよう、2つのルートを試す
    # 案1: /opt/wildlink/../common (期待値)
    # 案2: /home/ytsuchi/github/wildlink_project/common (絶対パス)
    
    paths_to_try = [
        os.path.abspath(os.path.join(base_dir, '..', 'common')),
        "/home/ytsuchi/github/wildlink_project/common"
    ]

    for p in paths_to_try:
        if os.path.exists(p):
            if p not in sys.path:
                sys.path.append(p)
            print(f"Added to sys.path: {p}")
            break

    # 診断対象
    UNITS = [
        'wmp_core',
        'units.unit_camera_v1',
        'utils.mqtt_client'
    ]

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