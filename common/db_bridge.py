import mysql.connector
import os
import json
from dotenv import load_dotenv
from datetime import datetime

class DBBridge:
    def __init__(self, dotenv_path=None):
        if dotenv_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            dotenv_path = os.path.join(os.path.dirname(current_dir), ".env")
        
        load_dotenv(dotenv_path)
        
        self.host = os.getenv('DB_HOST') or os.getenv('MQTT_BROKER')
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASS')
        self.database = os.getenv('DB_NAME')
        self.conn = None 
        
        if self.host is None:
             print(f"[DBBridge] ⚠️ WARNING: Host is None. Path: {dotenv_path}")

    def _get_connection(self):
        if self.conn is None or not self.conn.is_connected():
            if not self.host:
                raise ValueError("DBBridge Error: Host is not defined. Check .env path.")
            self.conn = mysql.connector.connect(
                host=self.host, user=self.user, password=self.password,
                database=self.database, connect_timeout=5, autocommit=True
            )
        else:
            try:
                self.conn.ping(reconnect=True, attempts=3, delay=1)
            except:
                self.conn = None
                return self._get_connection()
        return self.conn

    # --- 互換性維持のための汎用メソッド ---
    def _execute(self, sql, params=None):
        """古いコードが内部で利用している汎用実行メソッド"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(buffered=True)
            cursor.execute(sql, params or ())
            if not sql.strip().upper().startswith("SELECT"):
                conn.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"[DBBridge] Execute Error: {e}")
            return False

    def fetch_one(self, sql, params=None):
        """1件取得用"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(buffered=True)
            cursor.execute(sql, params or ())
            result = cursor.fetchone()
            cursor.close()
            return result
        except Exception as e:
            print(f"[DBBridge] FetchOne Error: {e}")
            return None

    # --- ログ管理機能 (NEW) ---
    def insert_system_log(self, sys_id, log_type, level, msg, code=0, ext=None):
        """system_logsテーブルへログを保存"""
        sql = """
            INSERT INTO system_logs (sys_id, log_type, log_level, log_msg, log_code, log_ext)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        return self._execute(sql, (sys_id, log_type, level, msg, code, ext))

    def get_log_level(self, sys_id):
        """nodesテーブルから設定されたログレベルを取得"""
        row = self.fetch_one("SELECT val_log_level FROM nodes WHERE sys_id = %s", (sys_id,))
        return row[0] if row else "info"

    # --- ステータス・ハートビート管理 ---
    def update_node_heartbeat(self, sys_id, status="online"):
        """main_manager.py 等から呼ばれる生存報告"""
        query = "UPDATE nodes SET sys_status = %s, last_seen = NOW() WHERE sys_id = %s"
        return self._execute(query, (status, sys_id))

    def update_vst_status(self, sys_id, vst_type, status):
        """node_status_current を更新"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            query = """
                UPDATE node_status_current 
                SET val_status = %s 
                WHERE sys_id = %s AND vst_type = %s
            """
            cursor.execute(query, (status, sys_id, vst_type))
            if cursor.rowcount == 0:
                insert_query = """
                    INSERT INTO node_status_current (sys_id, vst_type, val_status)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE val_status = VALUES(val_status)
                """
                cursor.execute(insert_query, (sys_id, vst_type, status))
            cursor.close()
            return True
        except Exception as e:
            print(f"[DBBridge] update_vst_status Error: {e}")
            return False

    # --- 構成情報取得 ---
    def fetch_node_config(self, node_id):
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT c.vst_type, c.val_params, c.val_enabled, c.vst_role_name, 
                       c.hw_driver, c.hw_bus_addr, c.val_unit_map,
                       cat.vst_class, cat.vst_module
                FROM node_configs c
                JOIN device_catalog cat ON c.vst_type = cat.vst_type
                WHERE c.sys_id = %s AND c.val_enabled = TRUE
            """
            cursor.execute(query, (node_id,))
            configs = cursor.fetchall()
            cursor.close()
            for cfg in configs:
                for key in ['val_params', 'val_unit_map']:
                    if cfg.get(key) and isinstance(cfg[key], str):
                        try:
                            cfg[key] = json.loads(cfg[key])
                        except: pass
            return configs
        except Exception as e:
            print(f"[DBBridge] Fetch Error: {e}")
            return None

    def fetch_vst_links(self, node_id):
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT source_role, target_role, event_type, val_interval FROM vst_links WHERE sys_id = %s AND val_enabled = 1"
            cursor.execute(query, (node_id,))
            links = cursor.fetchall()
            cursor.close()
            return links
        except Exception as e:
            print(f"[DBBridge] Link Fetch Error: {e}")
            return []

    # --- コマンド履歴管理 ---
    def update_node_status(self, node_id, payload):
        """node_commands 履歴更新用"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            now = datetime.now()
            if "cmd_id" in payload:
                cmd_id = payload["cmd_id"]
                val_status = payload.get("val_status", "success")
                sql = """
                    UPDATE node_commands 
                    SET val_status = %s, 
                        acked_at = IFNULL(acked_at, %s),
                        completed_at = CASE WHEN %s = 'success' THEN %s ELSE completed_at END
                    WHERE id = %s
                """
                cursor.execute(sql, (val_status, now, val_status, now, cmd_id))
            cursor.close()
            return True
        except Exception as e:
            print(f"[DBBridge] update_node_status Error: {e}")
            return False

    def fetch_pending_commands(self, node_id=None):
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM node_commands WHERE val_status = 'pending'"
            params = []
            if node_id:
                query += " AND sys_id = %s"
                params.append(node_id)
            cursor.execute(query, params)
            result = cursor.fetchall()
            cursor.close()
            return result
        except Exception as e:
            print(f"[DBBridge] fetch_pending_commands Error: {e}")
            return []

    def update_command_status(self, cmd_id, status):
        column_update = ""
        if status == "sent": column_update = ", sent_at = NOW(3)"
        elif status == "acked": column_update = ", acked_at = NOW(3)"
        elif status == "completed": column_update = ", completed_at = NOW(3)"
        query = f"UPDATE node_commands SET val_status = %s {column_update} WHERE id = %s"
        return self._execute(query, (status, cmd_id))