import subprocess
import socket
import paho.mqtt.client as mqtt
import json
import sys
import os
import threading
from wmp_core import WMPHeader

# グローバル変数として実体を置く（確実に1つだけにする）
controller = None

class CameraController:
    def __init__(self, node_id, hub_ip):
        self.node_id = node_id
        self.hub_ip = hub_ip
        self.wmp = WMPHeader(node_id=node_id, media_type=2)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.process = None
        self.is_streaming = False

    def start_stream(self):
        if self.process: 
            print("!!! Already streaming")
            return
        print(f"DEBUG: Starting FFmpeg for {self.hub_ip}:5005")
        cmd = ['ffmpeg', '-f', 'v4l2', '-i', '/dev/video0', '-s', '640x480', '-r', '10', '-f', 'mjpeg', '-q:v', '10', '-fflags', 'nobuffer', 'pipe:1']
        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.is_streaming = True
        threading.Thread(target=self._read_pipe, daemon=True).start()

    def _read_pipe(self):
        buffer = b""
        while self.process and self.process.poll() is None:
            chunk = self.process.stdout.read(4096)
            if not chunk: break
            buffer += chunk
            a, b = buffer.find(b'\xff\xd8'), buffer.find(b'\xff\xd9')
            if a != -1 and b != -1:
                frame = buffer[a:b+2]
                buffer = buffer[b+2:]
                # 送信ログ（多すぎるのでコメントアウト推奨だが、最初は1回だけ出す）
                self.wmp.send_large_data(self.sock, (self.hub_ip, 5005), frame, flags=1)

    def stop_stream(self):
        if self.process:
            print("DEBUG: Stopping FFmpeg")
            self.process.terminate()
            self.process = None
            self.is_streaming = False
            self.wmp.send_large_data(self.sock, (self.hub_ip, 5005), b"", flags=2)

# --- WildLink 規格 ---

def get_data(unit_cfg):
    global controller
    status = "Streaming" if (controller and controller.is_streaming) else "Idle"
    return True, {"log_msg": f"Camera Unit {status}"}

def start_monitoring(unit_cfg):
    global controller
    node_id = "node_001" 
    hub_ip = unit_cfg.get("net_ip", "192.168.0.102")
    
    controller = CameraController(node_id, hub_ip)
    
    def on_message(client, userdata, msg):
        print(f"DEBUG: MQTT Received Topic: {msg.topic}, Payload: {msg.payload}")
        try:
            payload = json.loads(msg.payload.decode())
            action = payload.get("act_stream")
            if action == "start":
                controller.start_stream()
            elif action == "stop":
                controller.stop_stream()
        except Exception as e:
            print(f"MQTT Parse Error: {e}")

    client = mqtt.Client()
    client.on_message = on_message
    # HubのIPに接続
    client.connect(hub_ip, 1883)
    # トピックを確実に購読
    topic = f"wildlink/{node_id}/control"
    client.subscribe(topic)
    print(f"DEBUG: Camera Monitor Subscribed to {topic}")
    client.loop_forever()