import sys
import os
import socket
import threading
import time
import json
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

# ロガー初期化 (log_type="stream_rx")
logger = get_logger("stream_rx")

# .envの読み込み
load_dotenv(os.path.join(wildlink_root, ".env"))

app = Flask(__name__)

# --- 2. データ抽象化レイヤー (StreamStore) ---
class StreamStore:
    def __init__(self):
        self.frames = {}
        self.last_update = {}
        self.assembly = {}
        self.is_streaming = {} 
        self.db = DBBridge()
        
        # 死活監視スレッドを起動
        threading.Thread(target=self._monitor_heartbeat, daemon=True).start()

    def _monitor_heartbeat(self):
        """パケット途絶を監視し、自動でステータスを idle に落とす"""
        while True:
            now = time.time()
            for port in list(self.last_update.keys()):
                # 5秒以上更新がない、かつ現在 'streaming' 状態なら idle へ
                if self.is_streaming.get(port) and (now - self.last_update.get(port, 0) > 5.0):
                    logger.warning(f"⏰ [Monitor] Port {port} timed out. Setting to idle.")
                    self.is_streaming[port] = False
                    self.sync_db_status(port, "idle")
            time.sleep(2)

    def sync_db_status(self, port, status):
        """node_status_current テーブルを更新する"""
        mapping = get_vst_mapping() 
        vst_type = next((k for k, v in mapping.items() if v == port), None)
        
        if not vst_type:
            return

        try:
            # DBBridgeを使用してステータス更新
            target_node = os.getenv("TARGET_NODE_ID", "node_001")
            self.db.update_vst_status(target_node, vst_type, status)
            logger.info(f"✅ [DB Sync] {vst_type} ({port}) -> {status}")
        except Exception as e:
            logger.error(f"❌ [DB Sync Error] {e}")

    def update_frame(self, port, frame):
        """UDP受信時に呼ばれる"""
        self.frames[port] = frame
        self.last_update[port] = time.time()
        
        if not self.is_streaming.get(port):
            self.is_streaming[port] = True
            self.sync_db_status(port, "streaming")

    def get_frame(self, port, timeout=3.0):
        """Flask配信時に呼ばれる"""
        if port not in self.frames or self.frames[port] is None:
            return None
        if time.time() - self.last_update.get(port, 0) > timeout:
            return None
        return self.frames[port]

    def clear(self, port):
        self.frames[port] = None
        self.last_update[port] = 0

store = StreamStore()

# --- 3. マッピング取得 ---
def get_vst_mapping():
    """node_configsテーブルから受信ポート一覧を取得"""
    db = DBBridge()
    mapping = {}
    my_id = os.getenv("HUB_SYS_ID", "hub_001") 

    try:
        # DBBridge経由で設定取得
        rows = db.fetch_node_config(my_id)
        if rows:
            for r in rows:
                v_type = r['vst_type']
                params = r.get('val_params', {})
                port = params.get("net_port")
                if port:
                    mapping[v_type] = int(port)
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
            p_len, f_idx, f_total = res[5], res[7], res[8]
            payload = data[32:32+p_len]

            if f_total == 1:
                store.update_frame(port, payload)
            else:
                if f_idx == 0:
                    store.assembly[port] = [None] * f_total
                
                if port in store.assembly:
                    store.assembly[port][f_idx] = payload
                    if all(v is not None for v in store.assembly[port]):
                        store.update_frame(port, b"".join(store.assembly[port]))
                        store.assembly[port] = []
        except Exception:
            time.sleep(0.001)

# --- 5. 配信レイヤー (HTTP MJPEG) ---
def generate_mjpeg(port):
    logger.info(f"🎬 [WMP RX] Client connected to port {port}")
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
                logger.warning(f"⚠️ [WMP RX] Timeout on port {port}. Closing connection.")
                break
            time.sleep(0.05) 
    finally:
        store.clear(port)

@app.route('/stream/<target>')
def stream(target):
    mapping = get_vst_mapping()
    
    # 互換性維持用
    if target == "pi": target = "cam_main"
    if target == "usb": target = "cam_sub"

    port = mapping.get(target)
    if not port:
        logger.error(f"❌ Target '{target}' not found in configs.")
        return f"Target '{target}' not found.", 404
    
    return Response(generate_mjpeg(port),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    initial_mapping = get_vst_mapping()
    
    for p in initial_mapping.values():
        t = threading.Thread(target=udp_receiver, args=(p,), daemon=True)
        t.start()
        
    logger.info(f"🚀 [HTTP] WildLink MJPEG Bridge started on port 8080")
    app.run(host='0.0.0.0', port=8080, threaded=True, debug=False)