import paho.mqtt.client as mqtt
import sys

# 規約に基づいた設定
BROKER_IP = "192.168.0.102"
NODE_ID = "node_001"
TOPIC = f"wildlink/{NODE_ID}/cmd"

def send_command(cmd):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "cmd_sender")
    try:
        client.connect(BROKER_IP, 1883, 60)
        client.publish(TOPIC, cmd)
        print(f"Sent '{cmd}' to {TOPIC}")
        client.disconnect()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 send_cmd.py [cam_start | cam_stop]")
    else:
        send_command(sys.argv[1])
