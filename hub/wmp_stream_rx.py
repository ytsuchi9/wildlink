import sys
import os
import socket
import threading
import time
import json
import mysql.connector
from flask import Flask, Response, request
from dotenv import load_dotenv

# --- 1. パス解決 (commonディレクトリへのパスを通す) ---
current_dir = os.path.dirname(os.path.abspath(__file__)) # hub/
wildlink_root = os.path.dirname(current_dir)             # wildlink/
common_path = os.path.join(wildlink_root, "common")

if common_path not in sys.path:
    sys.path.append(common_path)

from wmp_core import WMPHeader

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
        self._conn = None # 💡 接続を保持する変数

    def _get_db_conn(self):
        """DB接続を使い回し、切断されていれば再接続する"""
        if self._conn is None or not self._conn.is_connected():
            try:
                self._conn = mysql.connector.connect(
                    host=os.getenv("DB_HOST_LOCAL", "127.0.0.1"),
                    user=os.getenv("DB_USER"),
                    password=os.getenv("DB_PASS"),
                    database=os.getenv("DB_NAME"),
                    autocommit=True # 💡 即時反映
                )
            except Exception as e:
                print(f"❌ [DB Connection Error] {e}")
                return None
        return self._conn

    def sync_db_status(self, port, status):
        """node_status_current テーブルの val_status を更新する"""
        # ポートから vst_type を特定（逆引き）
        mapping = get_vst_mapping() 
        # mapping の key が 'cam_main' 等の vst_type (role名) になっています
        vst_type = next((k for k, v in mapping.items() if v == port), None)
        
        if not vst_type:
            return

        conn = self._get_db_conn()
        if conn:
            try:
                cursor = conn.cursor()
                # 💡 更新対象を node_status_current に変更
                target_node = os.getenv("TARGET_NODE_ID", "node_001")
                
                # ここがポイント：node_status_current を更新する
                query = """
                    UPDATE node_status_current 
                    SET val_status = %s 
                    WHERE vst_type = %s AND sys_id = %s
                """
                cursor.execute(query, (status, vst_type, target_node))
                
                # 万が一、レコードが存在しない場合に備えて
                if cursor.rowcount == 0 and status == "streaming":
                    insert_query = """
                        INSERT INTO node_status_current (sys_id, vst_type, val_status)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE val_status = VALUES(val_status)
                    """
                    cursor.execute(insert_query, (target_node, vst_type, status))
                
                cursor.close()
                print(f"✅ [DB Sync] {vst_type} ({port}) -> {status}")
            except Exception as e:
                print(f"❌ [DB Sync Error] {e}")

    def update_frame(self, port, frame):
        self.frames[port] = frame
        self.last_update[port] = time.time()
        
        # 💡 初回パケット受信時に 'streaming' へ更新
        if not self.is_streaming.get(port):
            self.is_streaming[port] = True
            # スレッドをブロックしないよう、必要ならここを非同期にしますが、まずは直列で。
            self.sync_db_status(port, "streaming")

    def get_frame(self, port, timeout=3.0):
        if port not in self.frames or self.frames[port] is None:
            return None
        if time.time() - self.last_update.get(port, 0) > timeout:
            # 💡 タイムアウト時にフラグを下ろす（DB更新は配信側で行う）
            self.is_streaming[port] = False
            return None
        return self.frames[port]

    def clear(self, port):
        self.frames[port] = None
        self.last_update[port] = 0

store = StreamStore()

# --- 3. DB連携 (最新カラム仕様準拠) ---
def get_vst_mapping():
    """node_configsテーブルから、Hubが担当する受信ポート一覧を取得する"""
    conn = None
    mapping = {}
    my_id = os.getenv("HUB_SYS_ID", "hub_001") 

    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST_LOCAL", "127.0.0.1"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            database=os.getenv("DB_NAME")
        )
        cursor = conn.cursor(dictionary=True)
        
        # sys_id が hub_001 の有効な設定を取得
        query = "SELECT vst_type, val_params FROM node_configs WHERE sys_id = %s AND val_enabled = 1"
        cursor.execute(query, (my_id,))
        rows = cursor.fetchall()
        
        for r in rows:
            v_type = r['vst_type']
            params = json.loads(r['val_params']) if r['val_params'] else {}
            port = params.get("net_port")
            if port:
                mapping[v_type] = int(port)
        
    except Exception as e:
        print(f"❌ [DB Error] {e}")
        # フォールバック設定 (DBが不調でも最低限動くように)
        mapping = {"cam_main": 5005, "cam_sub": 5006}
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            
    return mapping

# --- 4. 通信レイヤー (UDP) ---
def udp_receiver(port):
    """UDPパケットを受信し、Storeを更新する"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # ポートの再利用を許可 (再起動時のTimeWait対策)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
    print(f"📡 [WMP RX] Listening on UDP port {port}")
    
    while True:
        try:
            data, addr = sock.recvfrom(4096) # 余裕を持って受信
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
            time.sleep(0.01)

# --- 5. 配信レイヤー (HTTP MJPEG) ---
def generate_mjpeg(port):
    print(f"🎬 [WMP RX] Client connected to port {port}")
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
                # 3秒以上更新がない＝カメラ停止とみなし、一度切断する
                print(f"⚠️ [WMP RX] Timeout on port {port}. Closing connection.")
                break
            time.sleep(0.05) 
    finally:
        store.clear(port)

@app.route('/stream/<target>')
def stream(target):
    # リクエストごとに最新のマッピングを参照（動的な追加に対応）
    mapping = get_vst_mapping()
    
    # 互換性維持用の旧名対応
    if target == "pi": target = "cam_main"
    if target == "usb": target = "cam_sub"

    port = mapping.get(target)
    if not port:
        return f"Target '{target}' not found in Hub configurations.", 404
    
    return Response(generate_mjpeg(port),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # 起動時にDBからポート一覧を取得してリスナーをスレッド起動
    initial_mapping = get_vst_mapping()
    
    for p in initial_mapping.values():
        t = threading.Thread(target=udp_receiver, args=(p,), daemon=True)
        t.start()
        
    print(f"🚀 [HTTP] WildLink MJPEG Bridge started on port 8080")
    # threaded=True で複数ブラウザからの同時閲覧を許可
    app.run(host='0.0.0.0', port=8080, threaded=True, debug=False)