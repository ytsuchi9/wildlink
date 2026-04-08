import sys
import os
import socket
import threading
import time
import json
import paho.mqtt.client as mqtt
from flask import Flask, Response, request
from dotenv import load_dotenv

# --- 1. パス解決と初期設定 ---
current_dir = os.path.dirname(os.path.abspath(__file__)) 
wildlink_root = os.path.dirname(current_dir)
common_path = os.path.join(wildlink_root, "common")
if common_path not in sys.path:
    sys.path.append(common_path)

from wmp_core import WMPHeader
from db_bridge import DBBridge
from logger_config import get_logger

logger = get_logger("stream_rx")
load_dotenv(os.path.join(wildlink_root, ".env"))

# 🌟 .env からの動的読み込み
GROUP_ID   = os.getenv("GROUP_ID", "default_group")
HUB_ID     = os.getenv("HUB_ID", "hub_001")
MJPEG_PORT = int(os.getenv("MJPEG_PORT", "8080"))

app = Flask(__name__)

# --- 2. StreamStore: データ保持と状態監視 ---
class StreamStore:
    def __init__(self):
        self.frames = {}
        self.last_update = {}
        self.assembly = {}
        self.is_streaming = {}
        self.port_to_sysid = {} 
        self.port_to_role = {}
        self.db = DBBridge()
        
        # MQTT Client 初期化
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=f"hub_rx_{HUB_ID}")
        try:
            broker = os.getenv("MQTT_BROKER", "localhost")
            port = int(os.getenv("MQTT_PORT", 1883))
            self.mqtt_client.connect(broker, port, 60)
            self.mqtt_client.loop_start()
            logger.info(f"✅ [MQTT] Connected to {broker} as {HUB_ID}")
        except Exception as e:
            logger.error(f"❌ [MQTT] Connection failed: {e}")

        threading.Thread(target=self._monitor_heartbeat, daemon=True).start()

    def _monitor_heartbeat(self):
        """5秒以上の無信号でタイムアウト判定"""
        while True:
            now = time.time()
            for port in list(self.last_update.keys()):
                if self.is_streaming.get(port) and (now - self.last_update.get(port, 0) > 5.0):
                    role = self.port_to_role.get(port, "unknown")
                    sys_id = self.port_to_sysid.get(port, "unknown")
                    logger.warning(f"⏰ [Timeout] Stream for {role} (port:{port}) lost.")
                    
                    self.is_streaming[port] = False
                    self._sync_status(sys_id, role, "idle", msg="Stream timeout", code=408)
                    self.publish_wes_event(sys_id, role, "stream_lost")
            time.sleep(1)

    def _sync_status(self, sys_id, role, status, msg="Update", code=200):
        """DBの状態更新と、UIへの状態変化通知"""
        try:
            self.db.update_node_status(sys_id, role, {
                "val_status": status, 
                "log_msg": msg, 
                "log_code": code
            })
            # 状態変化そのものもブロードキャスト
            self.publish_wes_event(sys_id, role, "status_changed", {
                "val_status": status,
                "log_code": code
            })
        except Exception as e:
            logger.error(f"❌ [DB Sync Error] {e}")

    def update_frame(self, port, sys_id, frame):
        """フレーム完成時の処理"""
        self.frames[port] = frame
        self.last_update[port] = time.time()
        self.port_to_sysid[port] = sys_id
        
        if not self.is_streaming.get(port):
            self.is_streaming[port] = True
            role = self.port_to_role.get(port)
            if role:
                logger.info(f"🚀 [WMP RX] Streaming started: {role} (port:{port})")
                self._sync_status(sys_id, role, "streaming", msg="Stream initialized", code=200)
                # UIポップアップ用のキック
                self.publish_wes_event(sys_id, role, "stream_ready", {"net_port": port})

    def publish_wes_event(self, sys_id, role, event_name, extra=None):
        """WES 2026 準拠トピック"""
        payload = {
            "event": event_name,
            "time": int(time.time()),
            "sender": HUB_ID
        }
        if extra: payload.update(extra)
        topic = f"wildlink/{GROUP_ID}/{sys_id}/{role}/event"
        self.mqtt_client.publish(topic, json.dumps(payload))

    def get_frame(self, port, timeout=3.0):
        if port not in self.frames or self.frames[port] is None: return None
        if time.time() - self.last_update.get(port, 0) > timeout: return None
        return self.frames[port]

store = StreamStore()

# --- 3. 動的マッピング ---
def get_vst_mapping():
    db = DBBridge()
    mapping = {}
    try:
        rows = db.fetch_node_config(HUB_ID) # 🌟 自身のHUB_IDで設定を取得
        for r in rows:
            role = r.get('vst_role_name')
            params = r.get('val_params', {})
            port = params.get("net_port")
            if role and port:
                p_int = int(port)
                mapping[role] = p_int
                store.port_to_role[p_int] = role
    except Exception as e:
        logger.error(f"❌ [Mapping Error] {e}")
    return mapping

# --- 4. UDP 受信 ---
def udp_receiver(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    sock.bind(("0.0.0.0", port))
    
    logger.info(f"📡 [UDP] Listening on port {port}")
    
    while True:
        try:
            data, addr = sock.recvfrom(65535)
            header = WMPHeader.unpack(data)
            if not header: continue
            
            sys_id  = header[1]
            p_len   = header[5]
            f_id    = header[6] 
            f_idx   = header[7] 
            f_total = header[8] 
            
            payload = data[32:32+p_len]

            if f_total == 1:
                store.update_frame(port, sys_id, payload)
            else:
                if port not in store.assembly or store.assembly[port]["frame_id"] != f_id:
                    store.assembly[port] = {"frame_id": f_id, "chunks": [None] * f_total, "count": 0}

                target = store.assembly[port]
                if 0 <= f_idx < f_total and target["chunks"][f_idx] is None:
                    target["chunks"][f_idx] = payload
                    target["count"] += 1
                    
                    if target["count"] == f_total:
                        full_frame = b"".join(target["chunks"])
                        store.update_frame(port, sys_id, full_frame)
                        del store.assembly[port]

        except Exception as e:
            logger.error(f"❌ [UDP Error] Port {port}: {e}")
            time.sleep(0.01)

# --- 5. Flask API ---
def generate_mjpeg(port):
    last_h = None
    while True:
        frame = store.get_frame(port)
        if frame:
            curr_h = hash(frame)
            if curr_h != last_h:
                last_h = curr_h
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.01)
        else:
            time.sleep(0.5)

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
        
    logger.info(f"🚀 [WMP RX] MJPEG Bridge started on port {MJPEG_PORT} (Group: {GROUP_ID})")
    app.run(host='0.0.0.0', port=MJPEG_PORT, threaded=True, debug=False)