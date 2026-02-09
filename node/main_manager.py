import json
import os
import importlib
import time
import sys
import threading
from datetime import datetime
from utils.mqtt_client import MQTTClient

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r') as f:
        return json.load(f)

def main():
    config = load_config()
    
    # --- ここを修正：先に値を取り出す ---
    node_id = config.get("sys_node_id", "unknown_node")
    broker = config.get("net_broker_ip", "127.0.0.1")
    
    # 修正後の呼び出し（第1引数に broker、第2に node_id）
    mqtt = MQTTClient(broker, node_id) 
    
    # ノード共通情報
    interval = config.get("val_global_interval", 10)
    topic = f"wildlink/{node_id}/data"
    
    # ユニットを動的に読み込み
    loaded_units = {}
    for unit_cfg in config.get("units", []):
        if unit_cfg.get("val_enabled"):
            try:
                mod_name = unit_cfg['module']
                mod = importlib.import_module(f"units.{mod_name}")
                loaded_units[unit_cfg["name"]] = (mod, unit_cfg)
                
                # 特殊ユニット（ボタン監視など）をバックグラウンドスレッドで起動
                if hasattr(mod, 'start_monitoring'):
                    thread = threading.Thread(
                        target=mod.start_monitoring, 
                        args=(unit_cfg,), 
                        daemon=True
                    )
                    thread.start()
                    print(f"[{unit_cfg['name']}] Background monitor started.")
                
            except Exception as e:
                print(f"Failed to load unit {unit_cfg['name']}: {e}")

    print(f"Main loop started. Node: {node_id}, Interval: {interval}s")

    try:
        while True:
            combined_data = {
                "sys_node_id": node_id,
                "sys_time": datetime.now().isoformat(timespec='seconds')
            }

            # 各ユニットからデータを収集
            for name, (mod, unit_cfg) in loaded_units.items():
                success, data = mod.get_data(unit_cfg)
                if success:
                    combined_data.update(data)
                else:
                    # エラー時はログ情報を統合
                    combined_data.update(data)
                    print(f"[{name}] Error Code: {data.get('log_code')}")

            # MQTTで送信
            mqtt.publish(topic, combined_data)
            print(f"Published to {topic}: Success")
            print(f"Data: {combined_data}")
            print("-" * 30)

            time.sleep(interval)

    except KeyboardInterrupt:
        print("Stopped by user.")
    finally:
        mqtt.disconnect()

if __name__ == "__main__":
    main()