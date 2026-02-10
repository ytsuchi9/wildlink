import os
import sys
import time
import json
import importlib

# パス設定
current_dir = os.path.dirname(os.path.abspath(__file__))
common_path = os.path.abspath(os.path.join(current_dir, "../common"))
if common_path not in sys.path:
    sys.path.append(common_path)

from utils.mqtt_client import MQTTClient

active_units = []

def load_config():
    with open(os.path.join(current_dir, "config.json"), "r") as f:
        return json.load(f)

def load_units(unit_configs):
    units = []
    for cfg in unit_configs:
        if not cfg.get("val_enabled", True): continue
        driver = cfg.get("hw_driver")
        try:
            module = importlib.import_module(f"units.{driver}")
            unit_class = getattr(module, "WildLinkUnit")
            units.append(unit_class(cfg))
            print(f"[ OK ] Loaded: {cfg.get('val_name', driver)}")
        except Exception as e:
            print(f"[FAIL] {driver}: {e}")
    return units

def on_message(client, userdata, msg):
    global active_units
    try:
        payload = msg.payload.decode()
        print(f"\n[MQTT RECV] {payload}")
        
        target_strobe = None
        if "cam_start" in payload: target_strobe = True
        elif "cam_stop" in payload: target_strobe = False

        if target_strobe is not None:
            for unit in active_units:
                if hasattr(unit, 'act_strobe'):
                    unit.act_strobe = target_strobe
                    print(f">>> Camera act_strobe = {target_strobe}")
    except Exception as e:
        print(f"on_message error: {e}")

def main():
    global active_units
    config = load_config()
    sys_id = config.get("sys_id", "node_001")
    broker_ip = config.get("net_ip", "192.168.0.102")

    # --- 修正の要：以前のMQTTClientの引数に合わせる ---
    # 以前の定義: __init__(self, broker_address, client_id)
    try:
        mqtt = MQTTClient(broker_ip, sys_id)
        mqtt.connect()
    except Exception as e:
        print(f"MQTT Client Init Error: {e}")
        return

    mqtt.client.on_message = on_message
    mqtt.client.subscribe(f"wildlink/{sys_id}/cmd")
    # connect内でloop_start()されているはずですが、念のため
    
    print(f"--- Node {sys_id} Started ---")
    print(f"Connected to Broker: {broker_ip}")
    
    active_units = load_units(config.get("units", []))
    pub_topic = f"wildlink/{sys_id}/data"
    interval = config.get("val_interval", 10)

    try:
        while True:
            out_data = {
                "sys_id": sys_id,
                "sys_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "env_data": {},
                "log_msg": "Idle"
            }

            for unit in active_units:
                res = unit.update()
                if res: out_data["env_data"].update(res)
                if hasattr(unit, "log_msg") and unit.log_msg != "Idle":
                    out_data["log_msg"] = unit.log_msg

            mqtt.publish(pub_topic, out_data) # 以前のpublishは辞書のまま渡してOK
            print(f"\rStatus: {out_data['log_msg']} | Data: {len(out_data['env_data'])} items", end="")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        mqtt.disconnect()

if __name__ == "__main__":
    main()