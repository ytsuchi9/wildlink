import mysql.connector
from mysql.connector import Error
import os
import json
import logging
from dotenv import load_dotenv
from datetime import datetime

# 🌟 DBBridge専用のロガー（DBへの書き込みを行わず、コンソールのみ）
db_logger = logging.getLogger("db_bridge_safe")
if not db_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s - %(message)s')
    handler.setFormatter(formatter)
    db_logger.addHandler(handler)
    db_logger.setLevel(logging.ERROR)

class DBBridge:
    def __init__(self, dotenv_path=None):
        """初期化：.envからDB接続情報を読み込み、接続準備を行います。"""
        if dotenv_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            dotenv_path = os.path.join(os.path.dirname(current_dir), ".env")
        
        load_dotenv(dotenv_path)
        
        self.host = os.getenv('DB_HOST') or os.getenv('MQTT_BROKER')
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASS')
        self.database = os.getenv('DB_NAME')
        self.conn = None 
        
        if not self.host:
            db_logger.error(f"[DBBridge] ⚠️ DB_HOST is not defined in {dotenv_path}")

    def _get_connection(self):
        """DB接続の取得と再接続管理を行います。切断時は自動で再接続を試みます。"""
        if self.conn is None or not self.conn.is_connected():
            try:
                self.conn = mysql.connector.connect(
                    host=self.host, user=self.user, password=self.password,
                    database=self.database, connect_timeout=5, autocommit=True
                )
            except Error as e:
                db_logger.error(f"❌ Failed to connect to DB: {e}")
                raise
        else:
            try:
                self.conn.ping(reconnect=True, attempts=3, delay=1)
            except:
                self.conn = None
                return self._get_connection()
        return self.conn

    def execute(self, sql, params=None):
        """汎用実行メソッド (INSERT/UPDATE/DELETE用)。トランザクションをコミットします。"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(buffered=True)
            cursor.execute(sql, params or ())
            if not sql.strip().upper().startswith("SELECT"):
                conn.commit()
            cursor.close()
            return True
        except Exception as e:
            db_logger.error(f"🔥 [DBBridge] Execute Error: {e} | SQL: {sql}")
            return False

    def fetch_one(self, sql, params=None):
        """SELECT文を実行し、結果を辞書型で1件だけ取得します。"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute(sql, params or ())
            result = cursor.fetchone()
            cursor.close()
            return result
        except Exception as e:
            db_logger.error(f"[DBBridge] FetchOne Error: {e}")
            return None

    def fetch_all(self, sql, params=None):
        """SELECT文を実行し、該当するすべての結果を辞書型のリストで取得します。"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute(sql, params or ())
            result = cursor.fetchall()
            cursor.close()
            return result
        except Exception as e:
            db_logger.error(f"[DBBridge] FetchAll Error: {e}")
            return []

    # --- 📋 ログ・履歴管理 ---

    def insert_system_log(self, sys_id, log_type, level, msg, code=0, ext=None):
        """システム動作の履歴を system_logs テーブルに保存します。拡張データ(ext)はJSON化されます。"""
        sql = """
            INSERT INTO system_logs (sys_id, log_type, log_level, log_msg, log_code, log_ext)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        ext_json = json.dumps(ext, ensure_ascii=False) if ext else None
        return self.execute(sql, (sys_id, log_type, level, msg, code, ext_json))

    def insert_event_log(self, sys_id, vst_role_name, payload):
        """VSTユニットからのイベント（状態変化など）を system_logs テーブルに保存します。"""
        log_code = payload.get('log_code', 200)
        log_msg = payload.get('log_msg', f"Event from {vst_role_name}")
        level = payload.get('log_level', 'info')
        ext_json = json.dumps(payload, ensure_ascii=False)
        
        sql = """
            INSERT INTO system_logs (sys_id, log_type, log_level, log_msg, log_code, log_ext)
            VALUES (%s, 'event', %s, %s, %s, %s)
        """
        return self.execute(sql, (sys_id, level, log_msg, log_code, ext_json))

    # --- ⚙️ 設定・ノード状態管理 ---

    def update_node_heartbeat(self, sys_id, status="online"):
        """ノードの生存確認（死活監視）として、最終更新時刻とステータスを更新します。"""
        query = "UPDATE nodes SET sys_status = %s, updated_at = NOW() WHERE sys_id = %s AND is_active = 1"
        return self.execute(query, (status, sys_id))

    def update_node_status(self, sys_id, role, status_dict):
        """ノードまたは役割ごとの現在の物理状態（node_status_current）をJSON辞書をもとに更新します。"""
        allowed_keys = ['val_status', 'net_ip', 'sys_cpu_t', 'sys_volt', 'val_paused', 'log_msg', 'log_ext', 'log_code']
        clean_dict = {k: v for k, v in status_dict.items() if k in allowed_keys}
        if not clean_dict: return False

        fields = []
        values = []
        for k, v in clean_dict.items():
            fields.append(f"{k} = %s")
            values.append(json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)

        if role:
            query = f"UPDATE node_status_current SET {', '.join(fields)}, updated_at = NOW(3) WHERE sys_id = %s AND vst_role_name = %s"
            values.extend([sys_id, role])
        else:
            query = f"UPDATE node_status_current SET {', '.join(fields)}, updated_at = NOW(3) WHERE sys_id = %s"
            values.append(sys_id)
        return self.execute(query, tuple(values))

    def fetch_node_config(self, sys_id):
        """DBからノードの現在の動作設定パラメータ一式（node_configsとカタログのJOIN）を取得します。"""
        query = """
            SELECT c.vst_type, c.val_params, c.is_active, c.vst_role_name, 
                   c.hw_driver, c.hw_bus_addr, c.val_unit_map, cat.vst_class, cat.vst_module
            FROM node_configs c JOIN device_catalog cat ON c.vst_type = cat.vst_type
            WHERE c.sys_id = %s AND c.is_active = 1 AND cat.is_active = 1
        """
        configs = self.fetch_all(query, (sys_id,))
        for cfg in configs:
            for key in ['val_params', 'val_unit_map']:
                if cfg.get(key) and isinstance(cfg[key], str):
                    try: cfg[key] = json.loads(cfg[key])
                    except: pass
        return configs

    def fetch_vst_links(self, sys_id):
        """VST間の連動設定（例：人感センサー反応でカメラON）の一覧を取得します。"""
        query = "SELECT source_role, target_role, event_type, action_cmd, action_params, val_interval FROM vst_links WHERE sys_id = %s AND is_active = 1"
        links = self.fetch_all(query, (sys_id,))
        for l in links:
            if l.get('action_params') and isinstance(l['action_params'], str):
                try: l['action_params'] = json.loads(l['action_params'])
                except: pass
        return links

    def sync_node_config_from_payload(self, cmd_id, config_dict):
        """完了したコマンドの内容をもとに、DBのnode_configsを直接上書き更新(同期)します。"""
        res = self.fetch_one("SELECT sys_id, vst_role_name FROM node_commands WHERE id = %s", (cmd_id,))
        if not res: return
        
        sys_id = res['sys_id']
        role = res['vst_role_name']

        for key, value in config_dict.items():
            if key.startswith('val_') or key.startswith('act_'):
                sql = f"UPDATE node_configs SET {key} = %s WHERE sys_id = %s AND vst_role_name = %s"
                self.execute(sql, (value, sys_id, role))

    # --- 🛰️ コマンド・ライフサイクル管理 (WES 2026) ---

    def fetch_pending_commands(self, sys_id=None):
        """まだノードへ配送されていない(pending)状態のコマンドを古い順に取得します。"""
        query = "SELECT * FROM node_commands WHERE val_status = 'pending'"
        params = []
        if sys_id:
            query += " AND sys_id = %s"
            params.append(sys_id)
        query += " ORDER BY created_at ASC"
        return self.fetch_all(query, params)

    def update_command_status(self, cmd_id, status, log_msg=None):
        """コマンドの状態（sentやacknowledged等）と、それに応じた時刻スタンプを更新します。"""
        if not cmd_id or cmd_id == 0: return False
        
        timestamp_col = ""
        if status == "sent": timestamp_col = ", sent_at = NOW(3)"
        elif status == "acknowledged": timestamp_col = ", acked_at = NOW(3)"
        
        sql = f"UPDATE node_commands SET val_status = %s, log_msg = %s {timestamp_col} WHERE id = %s"
        return self.execute(sql, (status, log_msg, cmd_id))

    def mark_command_acknowledged(self, cmd_id):
        """ノードからの受領確認（ACK）を受け、acked_atに時刻を記録します（逆転防止ガード付き）。"""
        sql = """
            UPDATE node_commands SET acked_at = NOW(3), val_status = 'acknowledged' 
            WHERE id = %s AND acked_at IS NULL AND val_status NOT IN ('completed', 'error')
        """
        return self.execute(sql, (cmd_id,))

    def finalize_command(self, cmd_id, status, log_msg='', log_code=200, res_payload=None):
        """コマンドの最終決着（completed/error等）を行い、completed_atに時刻を記録して処理を終了します。"""
        if not cmd_id or cmd_id == 0: return False
        res_json = json.dumps(res_payload, ensure_ascii=False) if res_payload else None
        sql = """
            UPDATE node_commands 
            SET val_status = %s, log_msg = %s, log_code = %s, val_res_payload = %s, completed_at = NOW(3) 
            WHERE id = %s
        """
        return self.execute(sql, (status, log_msg, log_code, res_json, cmd_id))