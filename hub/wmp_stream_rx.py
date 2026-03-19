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
        self.frames = {}        # {port: b"jpeg_data"}
        self.last_update = {}   # {port: timestamp}
        self.assembly = {}      # {port: [chunks]}
        self.is_streaming = {}  # {port: bool}
        self.port_to_sysid = {} # {port: "node_001"} 💡動的識別のために追加
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
                    sys_id = self.port_to_sysid.get(port, "unknown")
                    logger.warning(f"⏰ [Monitor] Port {port} ({sys_id}) timed out. Setting to idle.")
                    self.is_streaming[port] = False
                    self.sync_db_status(port, sys_id, "idle")
            time.sleep(2)

    def sync_db_status(self, port, sys_id, status):
        """node_status_current テーブルを更新する"""
        mapping = get_vst_mapping() 
        vst_type = next((k for k, v in mapping.items() if v == port), None)
        
        if not vst_type or sys_id == "unknown":
            return

        try:
            # 💡 修正：TARGET_NODE_ID の固定をやめ、パケットから得た sys_id を使用
            self.db.update_vst_status(sys_id, vst_type, status)
            logger.info(f"✅ [DB Sync] {sys_id}:{vst_type} ({port}) -> {status}")
        except Exception as e:
            logger.error(f"❌ [DB Sync Error] {e}")

    def update_frame(self, port, sys_id, frame):
        """UDP受信・結合完了時に呼ばれる"""
        self.frames[port] = frame
        self.last_update[port] = time.time()
        self.port_to_sysid[port] = sys_id
        
        if not self.is_streaming.get(port):
            self.is_streaming[port] = True
            # ストリーミング開始をDBに通知
            self.sync_db_status(port, sys_id, "streaming")

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

# --- 3. マッピング取得 (Role-Based版) ---
def get_vst_mapping():
    """node_configsテーブルから '役割名:ポート' のマッピングを取得"""
    db = DBBridge()
    mapping = {}
    my_id = os.getenv("SYS_ID", "hub_001") 

    try:
        rows = db.fetch_node_config(my_id)
        if rows:
            for r in rows:
                # 2026仕様: vst_type ではなく vst_role_name を識別子にする
                role_name = r.get('vst_role_name')
                params = r.get('val_params', {})
                port = params.get("net_port")
                if role_name and port:
                    mapping[role_name] = int(port)
        
        logger.info(f"📋 Loaded Role-Port Mapping: {mapping}")
    except Exception as e:
        logger.error(f"❌ [Mapping Error] {e}")
        # フォールバック
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
            # WMPHeader.unpack を使用してパケットを解析
            res = WMPHeader.unpack(data)
            sys_id = res[1]      # パケット内蔵のノードID (sys_id)
            p_len = res[5]       # ペイロード長
            f_idx = res[7]       # 分割インデックス
            f_total = res[8]     # 総分割数
            
            payload = data[32:32+p_len]

            if f_total == 1:
                # 単一パケットの場合
                store.update_frame(port, sys_id, payload)
            else:
                # 分割パケットの結合処理
                if f_idx == 0:
                    store.assembly[port] = [None] * f_total
                
                if port in store.assembly:
                    store.assembly[port][f_idx] = payload
                    # 全パーツが揃ったか確認
                    if all(v is not None for v in store.assembly[port]):
                        full_frame = b"".join(store.assembly[port])
                        store.update_frame(port, sys_id, full_frame)
                        store.assembly[port] = []
        except Exception as e:
            # 頻発するエラーはスルー、重大なものだけログ
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
                # 映像が途切れたらループ終了
                logger.warning(f"⚠️ [WMP RX] No data on port {port}. Closing stream.")
                break
            time.sleep(0.04) # 約25fps
    finally:
        store.clear(port)

@app.route('/stream/<target>')
def stream(target):
    # CameraUnit.js から /stream/cam_main 等でリクエストが来る
    mapping = get_vst_mapping()
    port = mapping.get(target)

    if not port:
        logger.error(f"❌ Target Role '{target}' not found in configs.")
        return f"Role '{target}' not found.", 404
    
    return Response(generate_mjpeg(port),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # 起動時に必要なポートのマッピングを取得
    initial_mapping = get_vst_mapping()
    
    # 各ポートごとに受信スレッドを開始
    for p in initial_mapping.values():
        t = threading.Thread(target=udp_receiver, args=(p,), daemon=True)
        t.start()
        
    logger.info(f"🚀 [HTTP] WildLink MJPEG Bridge started on port 8080")
    # Flaskサーバ起動
    app.run(host='0.0.0.0', port=8080, threaded=True, debug=False)