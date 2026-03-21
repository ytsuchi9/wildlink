import sys
import os
import socket
import threading
import time
import json
import paho.mqtt.client as mqtt
from flask import Flask, Response, request
from dotenv import load_dotenv

# --- 1. パス解決 ---
current_dir = os.path.dirname(os.path.abspath(__file__)) 
wildlink_root = os.path.dirname(current_dir)
common_path = os.path.join(wildlink_root, "common")

if common_path not in sys.path:
    sys.path.append(common_path)

from wmp_core import WMPHeader
from db_bridge import DBBridge
from logger_config import get_logger

# ロガー初期化
logger = get_logger("stream_rx")

# .envの読み込み
load_dotenv(os.path.join(wildlink_root, ".env"))

app = Flask(__name__)

# --- 2. データ抽象化レイヤー (StreamStore) ---
class StreamStore:
    def __init__(self):
        self.frames = {}        # {port: b"jpeg_data"}
        self.last_update = {}   # {port: timestamp}
        self.assembly = {}      # {port: [chunks]}
        self.is_streaming = {}  # {port: bool}
        self.port_to_sysid = {} 
        self.port_to_role = {}  # 💡 逆引き用 {5005: "cam_main"}
        self.db = DBBridge()
        
        # MQTTクライアントの初期化 (WES規格用)
        self.mqtt_client = mqtt.Client()
        try:
            self.mqtt_client.connect("localhost", 1883, 60)
            self.mqtt_client.loop_start()
            logger.info("✅ [MQTT] Connected to local broker for WES events.")
        except Exception as e:
            logger.error(f"❌ [MQTT] Connection failed: {e}")

        # 死活監視スレッドを起動
        threading.Thread(target=self._monitor_heartbeat, daemon=True).start()

    def _monitor_heartbeat(self):
        while True:
            now = time.time()
            for port in list(self.last_update.keys()):
                if self.is_streaming.get(port) and (now - self.last_update.get(port, 0) > 5.0):
                    sys_id = self.port_to_sysid.get(port, "unknown")
                    logger.warning(f"⏰ [Monitor] Port {port} ({sys_id}) timed out. Setting to idle.")
                    self.is_streaming[port] = False
                    self.sync_db_status(port, sys_id, "idle")
            time.sleep(2)

    def sync_db_status(self, port, sys_id, status):
        """DB更新と同時に MQTT でストップイベントを飛ばす"""
        role_name = self.port_to_role.get(port)
        if not role_name or sys_id == "unknown": return

        try:
            self.db.update_vst_status(sys_id, role_name, status)
            if status == "idle":
                # WES規格: 停止も通知
                self.publish_wes_event(role_name, "stream_stop")
            logger.info(f"✅ [DB Sync] {sys_id}:{role_name} -> {status}")
        except Exception as e:
            logger.error(f"❌ [DB Sync Error] {e}")

    def update_frame(self, port, sys_id, frame):
        """UDP受信・結合完了時に呼ばれる"""
        self.frames[port] = frame
        self.last_update[port] = time.time()
        self.port_to_sysid[port] = sys_id
        
        # 💡 ストリーミング開始の瞬間を検知
        if not self.is_streaming.get(port):
            self.is_streaming[port] = True
            role_name = self.port_to_role.get(port)
            
            # 1. DBステータスを streaming に
            self.sync_db_status(port, sys_id, "streaming")
            
            # 2. 💡 WES規格: MQTTで stream_ready をブロードキャスト
            # これを Web(JS) が受けて映像表示を開始する
            if role_name:
                self.publish_wes_event(role_name, "stream_ready")

    def publish_wes_event(self, role, event_type):
        """WildLink Event Standard (WES) に基づくメッセージ発行"""
        payload = {
            "event": event_type,
            "role": role,
            "time": int(time.time()),
            "msg": f"Stream event: {event_type}"
        }
        topic = f"_local/vst/event" # VstManagerが購読しているトピック
        self.mqtt_client.publish(topic, json.dumps(payload))
        logger.info(f"🔔 [WES] Published '{event_type}' for {role} to {topic}")

    def get_frame(self, port, timeout=3.0):
        if port not in self.frames or self.frames[port] is None: return None
        if time.time() - self.last_update.get(port, 0) > timeout: return None
        return self.frames[port]

    def clear(self, port):
        self.frames[port] = None
        self.last_update[port] = 0

store = StreamStore()

# --- 3. マッピング取得 ---
def get_vst_mapping():
    db = DBBridge()
    mapping = {}
    my_id = os.getenv("SYS_ID", "hub_001") 
    try:
        rows = db.fetch_node_config(my_id)
        if rows:
            for r in rows:
                role_name = r.get('vst_role_name')
                params = r.get('val_params', {})
                port = params.get("net_port")
                if role_name and port:
                    p_int = int(port)
                    mapping[role_name] = p_int
                    store.port_to_role[p_int] = role_name # 逆引きもセット
        logger.info(f"📋 Loaded Role-Port Mapping: {mapping}")
    except Exception as e:
        logger.error(f"❌ [Mapping Error] {e}")
        mapping = {"cam_main": 5005, "cam_sub": 5006}
    return mapping

# --- 4. 通信レイヤー (UDP) ---
def udp_receiver(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
    logger.info(f"📡 [WMP RX] Listening on UDP port {port}")
    
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            res = WMPHeader.unpack(data)
            sys_id = res[1]
            p_len = res[5]
            f_idx = res[7]
            f_total = res[8]
            payload = data[32:32+p_len]

            if f_total == 1:
                store.update_frame(port, sys_id, payload)
            else:
                if f_idx == 0:
                    store.assembly[port] = [None] * f_total
                
                if port in store.assembly:
                    store.assembly[port][f_idx] = payload
                    if all(v is not None for v in store.assembly[port]):
                        full_frame = b"".join(store.assembly[port])
                        store.update_frame(port, sys_id, full_frame)
                        store.assembly[port] = []
        except Exception:
            time.sleep(0.001)

# --- 5. 配信レイヤー (HTTP MJPEG) ---
def generate_mjpeg(port):
    logger.info(f"🎬 [WMP RX] Client connected to MJPEG Bridge on port {port}")
    last_h = None
    try:
        while True:
            frame = store.get_frame(port)
            if frame:
                curr_h = hash(frame)
                if curr_h != last_h:
                    last_h = curr_h
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                logger.warning(f"⚠️ [WMP RX] Stream timed out on port {port}.")
                break
            time.sleep(0.04)
    finally:
        # クライアントが切断しても、UDP受信スレッドが動いている限り store.frames は維持される
        pass

@app.route('/stream/<target>')
def stream(target):
    mapping = get_vst_mapping()
    port = mapping.get(target)
    if not port:
        return f"Role '{target}' not found.", 404
    return Response(generate_mjpeg(port),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    initial_mapping = get_vst_mapping()
    for p in initial_mapping.values():
        t = threading.Thread(target=udp_receiver, args=(p,), daemon=True)
        t.start()
        
    logger.info(f"🚀 [HTTP] WildLink MJPEG Bridge started on port 8080")
    app.run(host='0.0.0.0', port=8080, threaded=True, debug=False)