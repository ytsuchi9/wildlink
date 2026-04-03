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
        self.assembly = {}       # {port: {"frame_id": int, "chunks": [None]}}
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
                    logger.warning(f"⏰ [Timeout] Stream for {role} (port:{port}) lost.")
                    
                    self.is_streaming[port] = False
                    self._sync_status(sys_id, role, "idle")
                    self.publish_wes_event(sys_id, role, "stream_lost")
            time.sleep(2)

    def _sync_status(self, sys_id, role, status):
        """DBの状態を更新"""
        try:
            self.db.update_node_status(sys_id, role, {"val_status": status, "log_msg": "RX monitor update"})
        except Exception as e:
            logger.error(f"❌ [DB Sync Error] {e}")

    def update_frame(self, port, sys_id, frame):
        """UDP受信スレッドから呼ばれる。新しいフレームが完成した時の処理"""
        self.frames[port] = frame
        self.last_update[port] = time.time()
        self.port_to_sysid[port] = sys_id
        
        # 初回受信時の「ストリーミング開始」検知
        if not self.is_streaming.get(port):
            self.is_streaming[port] = True
            role = self.port_to_role.get(port)
            if role:
                logger.info(f"🚀 [WMP RX] Streaming started: {role} (port:{port})")
                self._sync_status(sys_id, role, "streaming")
                self.publish_wes_event(sys_id, role, "stream_ready", {"net_port": port})

    def publish_wes_event(self, sys_id, role, event_name, extra=None):
        payload = {
            "event": event_name,
            "val_status": "streaming" if "ready" in event_name else "idle",
            "time": int(time.time())
        }
        if extra: payload.update(extra)
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
        rows = db.fetch_node_config(hub_id)
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

# --- 4. UDP 受信スレッド ---
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
            
            # header = (ver, sys_id, role, f_id, seq, p_len, f_idx, f_total)
            # wmp_core.py の pack 順序に合わせてインデックスを厳密に指定
            sys_id = header[1]
            f_id   = header[3]
            p_len  = header[5]
            f_idx  = header[6]
            f_total= header[7]
            
            payload = data[32:32+p_len]

            if f_total == 1:
                store.update_frame(port, sys_id, payload)
            else:
                # 1. 未知のポート、または新しいフレームIDが来たら初期化
                if port not in store.assembly or store.assembly[port]["frame_id"] != f_id:
                    # f_total が異常な値（巨大すぎるなど）でないか簡易チェック
                    if 0 < f_total < 1000: 
                        store.assembly[port] = {"frame_id": f_id, "chunks": [None] * f_total}
                    else:
                        continue

                # 2. 境界チェック（ここが index out of range 対策！）
                if 0 <= f_idx < len(store.assembly[port]["chunks"]):
                    store.assembly[port]["chunks"][f_idx] = payload
                    
                    # 3. 全チャンクが揃ったか確認
                    if all(v is not None for v in store.assembly[port]["chunks"]):
                        full_frame = b"".join(store.assembly[port]["chunks"])
                        store.update_frame(port, sys_id, full_frame)
                        # メモリ節約のため、完了したフレームの chunks はクリア
                        store.assembly[port]["chunks"] = [] 
                else:
                    logger.debug(f"⚠️ [UDP] Invalid chunk index: {f_idx}/{f_total}")

        except Exception as e:
            # ログが溢れないよう、エラー内容を具体的に出力
            logger.error(f"❌ [UDP Error] Port {port}: {type(e).__name__}: {e}")
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
            time.sleep(0.01) # 最速で送信
        else:
            # タイムアウトした場合はNO SIGNAL画像を表示するか、コネクションを閉じる
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
    # 起動時に必要な全ポートのスレッドを開始
    initial_mapping = get_vst_mapping()
    for p in initial_mapping.values():
        t = threading.Thread(target=udp_receiver, args=(p,), daemon=True)
        t.start()
        
    logger.info(f"🚀 [WMP RX] MJPEG Bridge started on port 8080")
    # debug=False にしないとスレッドが二重起動するので注意
    app.run(host='0.0.0.0', port=8080, threaded=True, debug=False)