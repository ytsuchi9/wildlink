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

app = Flask(__name__)

# --- 2. StreamStore: データ保持と状態監視 ---
class StreamStore:
    def __init__(self):
        self.frames = {}         # {port: b"jpeg_data"}
        self.last_update = {}    # {port: timestamp}
        self.assembly = {}       # {port: [chunks]}
        self.is_streaming = {}   # {port: bool}
        self.port_to_sysid = {} 
        self.port_to_role = {}   # {5005: "cam_main"}
        self.db = DBBridge()
        
        # WES 2026: Hub Manager 経由で UI に通知するため MQTT を使用
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="hub_stream_rx")
        try:
            self.mqtt_client.connect("localhost", 1883, 60)
            self.mqtt_client.loop_start()
            logger.info("✅ [MQTT] Connected to broker for WES signals.")
        except Exception as e:
            logger.error(f"❌ [MQTT] Connection failed: {e}")

        # ハートビート（死活監視）スレッド
        threading.Thread(target=self._monitor_heartbeat, daemon=True).start()

    def _monitor_heartbeat(self):
        """5秒以上パケットが途切れたら自動的に 'idle' へ落とす"""
        while True:
            now = time.time()
            for port in list(self.last_update.keys()):
                if self.is_streaming.get(port) and (now - self.last_update.get(port, 0) > 5.0):
                    role = self.port_to_role.get(port, "unknown")
                    sys_id = self.port_to_sysid.get(port, "unknown")
                    logger.warning(f"⏰ [Timeout] Stream for {role} (port:{port}) lost. Cleaning up.")
                    
                    self.is_streaming[port] = False
                    self._sync_status(sys_id, role, "idle")
                    # UI側にも停止を伝える
                    self.publish_wes_event(sys_id, role, "stream_lost")
            time.sleep(2)

    def _sync_status(self, sys_id, role, status):
        """DBの状態を更新"""
        try:
            # 物理状態を DB に同期
            self.db.update_node_status(sys_id, role, {"val_status": status, "log_msg": "Set by RX monitor"})
        except Exception as e:
            logger.error(f"❌ [DB Sync Error] {e}")

    def update_frame(self, port, sys_id, frame):
        """UDP受信スレッドから呼ばれる"""
        self.frames[port] = frame
        self.last_update[port] = time.time()
        self.port_to_sysid[port] = sys_id
        
        # 初回受信時の「ストリーミング開始」検知
        if not self.is_streaming.get(port):
            self.is_streaming[port] = True
            role = self.port_to_role.get(port)
            if role:
                logger.info(f"🚀 [WMP RX] First frame received for {role} on port {port}.")
                # 1. DBを更新
                self._sync_status(sys_id, role, "streaming")
                # 2. UIキック用の WES イベントを発行（Hub Manager が中継する）
                self.publish_wes_event(sys_id, role, "stream_ready", {"net_port": port})

    def publish_wes_event(self, sys_id, role, event_name, extra=None):
        """Hub Manager が拾える形式で MQTT イベントをパブリッシュ"""
        payload = {
            "event": event_name,
            "val_status": "streaming" if "ready" in event_name else "idle",
            "time": int(time.time())
        }
        if extra:
            payload.update(extra)
            
        topic = f"nodes/{sys_id}/{role}/event"
        self.mqtt_client.publish(topic, json.dumps(payload))

    def get_frame(self, port, timeout=3.0):
        if port not in self.frames or self.frames[port] is None: return None
        if time.time() - self.last_update.get(port, 0) > timeout: return None
        return self.frames[port]

store = StreamStore()

# --- 3. 動的マッピングの取得 ---
def get_vst_mapping():
    db = DBBridge()
    mapping = {}
    hub_id = os.getenv("SYS_ID", "hub_001") 
    try:
        # DBから自身の管理下にあるVSTの設定（ポート番号など）を取得
        rows = db.fetch_node_config(hub_id)
        for r in rows:
            role = r.get('vst_role_name')
            params = r.get('val_params', {})
            port = params.get("net_port")
            if role and port:
                p_int = int(port)
                mapping[role] = p_int
                store.port_to_role[p_int] = role
        logger.debug(f"📋 VST-Port Mapping: {mapping}")
    except Exception as e:
        logger.error(f"❌ [Mapping Error] {e}")
    return mapping

# --- 4. UDP 受信スレッド ---
def udp_receiver(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # バッファサイズを拡張（パケット落ち対策）
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
    sock.bind(("0.0.0.0", port))
    
    logger.info(f"📡 [UDP] Receiver started on port {port}")
    
    while True:
        try:
            data, addr = sock.recvfrom(65535)
            # WMP ヘッダー解読
            res = WMPHeader.unpack(data)
            if not res: continue
            
            sys_id, p_len, f_idx, f_total = res[1], res[5], res[7], res[8]
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
        except Exception as e:
            logger.error(f"❌ [UDP Error] Port {port}: {e}")
            time.sleep(0.01)

# --- 5. Flask MJPEG 配信 ---
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
        else:
            # 映像が途切れたらNO SIGNAL的な画像を出すか終了する
            break
        time.sleep(0.05) # 約20fps制限でCPU負荷軽減

@app.route('/stream/<target>')
def stream(target):
    mapping = get_vst_mapping()
    port = mapping.get(target)
    if not port:
        return f"Role '{target}' not found.", 404
    
    return Response(generate_mjpeg(port),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # 起動時に一度マッピングを確認してスレッドを開始
    initial_mapping = get_vst_mapping()
    for p in initial_mapping.values():
        t = threading.Thread(target=udp_receiver, args=(p,), daemon=True)
        t.start()
        
    logger.info(f"🚀 [HTTP] MJPEG Bridge started on port 8080")
    app.run(host='0.0.0.0', port=8080, threaded=True, debug=False)