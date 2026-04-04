import mysql.connector
from mysql.connector import Error
import os
import json
import logging
from dotenv import load_dotenv
from datetime import datetime

# 🌟 DBBridge専用のロガー（DBには書き込まず、コンソールにだけ出す）
# これにより、循環インポートと無限ループを両方回避します
db_logger = logging.getLogger("db_bridge_safe")
if not db_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s - %(message)s')
    handler.setFormatter(formatter)
    db_logger.addHandler(handler)
    db_logger.setLevel(logging.ERROR)

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

    def execute(self, sql, params=None):
        """汎用実行メソッド (CUD操作用)"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(buffered=True)
            cursor.execute(sql, params or ())
            # SELECT以外のクエリでコミットを確実に行う
            if not sql.strip().upper().startswith("SELECT"):
                conn.commit()
            cursor.close()
            return True
        except Exception as e:
            # --- ここからデバッグ用修正 ---
            # 🌟 安全なロガーで出力。これなら無限ループしません
            db_logger.error("-" * 50)
            db_logger.error(f"🔥 [DBBridge] Execute Error: {e}")
            db_logger.error(f"📍 SQL: {sql}")
            db_logger.error("-" * 50)
            # --- ここまで ---
            return False

    def fetch_one(self, sql, params=None):
        """1件取得用 (辞書形式)"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute(sql, params or ())
            result = cursor.fetchone()
            cursor.close()
            return result
        except Exception as e:
            print(f"[DBBridge] FetchOne Error: {e}")
            return None

    def fetch_all(self, sql, params=None):
        """全件取得用 (辞書形式のリスト)"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute(sql, params or ())
            result = cursor.fetchall()
            cursor.close()
            return result
        except Exception as e:
            print(f"[DBBridge] FetchAll Error: {e}")
            return []

    def insert_system_log(self, sys_id, log_type, level, msg, code=0, ext=None):
        sql = """
            INSERT INTO system_logs (sys_id, log_type, log_level, log_msg, log_code, log_ext)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        ext_json = json.dumps(ext, ensure_ascii=False) if ext else None
        return self.execute(sql, (sys_id, log_type, level, msg, code, ext_json))

    def insert_event_log(self, sys_id, vst_role_name, payload):
        log_code = payload.get('log_code', 200)
        log_msg = payload.get('log_msg', f"Event from {vst_role_name}")
        level = payload.get('log_level', 'info')
        ext_json = json.dumps(payload, ensure_ascii=False)
        
        sql = """
            INSERT INTO system_logs (sys_id, log_type, log_level, log_msg, log_code, log_ext)
            VALUES (%s, 'event', %s, %s, %s, %s)
        """
        return self.execute(sql, (sys_id, level, log_msg, log_code, ext_json))

    def update_node_heartbeat(self, sys_id, status="online"):
        query = "UPDATE nodes SET sys_status = %s, updated_at = NOW() WHERE sys_id = %s AND is_active = 1"
        return self.execute(query, (status, sys_id))

    def update_node_status(self, sys_id, role, status_dict):
        # 許可されたキーのみ抽出
        allowed_keys = ['val_status', 'net_ip', 'sys_cpu_t', 'sys_volt', 'val_paused', 'log_msg', 'log_ext', 'log_code']
        clean_dict = {k: v for k, v in status_dict.items() if k in allowed_keys}

        if 'val_status' in clean_dict and isinstance(clean_dict['val_status'], str):
            clean_dict['val_status'] = clean_dict['val_status'][:20]

        if not clean_dict: return False

        fields = []
        values = []
        for k, v in clean_dict.items():
            fields.append(f"{k} = %s")
            # 🌟 [修正] 値が dict や list の場合は JSON 文字列に変換する
            if isinstance(v, (dict, list)):
                values.append(json.dumps(v, ensure_ascii=False))
            else:
                values.append(v)

        if role:
            query = f"UPDATE node_status_current SET {', '.join(fields)}, updated_at = NOW(3) WHERE sys_id = %s AND vst_role_name = %s"
            values.extend([sys_id, role])
        else:
            query = f"UPDATE node_status_current SET {', '.join(fields)}, updated_at = NOW(3) WHERE sys_id = %s"
            values.append(sys_id)

        return self.execute(query, tuple(values))

    def fetch_node_config(self, sys_id):
        query = """
            SELECT c.vst_type, c.val_params, c.is_active, c.vst_role_name, 
                   c.hw_driver, c.hw_bus_addr, c.val_unit_map,
                   cat.vst_class, cat.vst_module
            FROM node_configs c
            JOIN device_catalog cat ON c.vst_type = cat.vst_type
            WHERE c.sys_id = %s AND c.is_active = 1 AND cat.is_active = 1
        """
        configs = self.fetch_all(query, (sys_id,))
        
        for cfg in configs:
            for key in ['val_params', 'val_unit_map']:
                if cfg.get(key) and isinstance(cfg[key], str):
                    try:
                        cfg[key] = json.loads(cfg[key])
                    except: pass
        return configs

    # (以下、他のメソッドも self._execute を self.execute に書き換えてお使いください)
    def fetch_vst_links(self, sys_id):
        query = """
            SELECT source_role, target_role, event_type, action_cmd, action_params, val_interval 
            FROM vst_links 
            WHERE sys_id = %s AND is_active = 1
        """
        links = self.fetch_all(query, (sys_id,))
        for link in links:
            if link.get('action_params') and isinstance(link['action_params'], str):
                try:
                    link['action_params'] = json.loads(link['action_params'])
                except: pass
        return links

    def fetch_pending_commands(self, sys_id=None):
        query = "SELECT * FROM node_commands WHERE val_status = 'pending'"
        params = []
        if sys_id:
            query += " AND sys_id = %s"
            params.append(sys_id)
        query += " ORDER BY created_at ASC" 
        return self.fetch_all(query, params)

    def update_command_status(self, cmd_id, status):
        if not cmd_id or cmd_id == 0: return False
        
        column_update = ""
        if status == "sent": 
            column_update = ", sent_at = NOW(3)"
        elif status == "acknowledged": 
            column_update = ", acked_at = NOW(3)"
            
        query = f"UPDATE node_commands SET val_status = %s {column_update} WHERE id = %s"
        return self.execute(query, (status, cmd_id))

    def mark_command_acknowledged(self, cmd_id):
        """ コマンド受領処理 (WES 2026: ステータス逆転防止ガード付き) """
        sql = """
            UPDATE node_commands 
            SET acked_at = NOW(3), val_status = 'acknowledged' 
            WHERE id = %s 
              AND acked_at IS NULL 
              AND val_status NOT IN ('completed', 'error')
        """
        return self.execute(sql, (cmd_id,))

    def finalize_command(self, cmd_id, status, log_msg='', log_code=200, res_payload=None):
        if not cmd_id or cmd_id == 0: return False
        final_status = status if status in ["success", "completed", "error"] else "error"
        res_json = json.dumps(res_payload, ensure_ascii=False) if res_payload else None
        
        # 🌟 log_ext ではなく log_msg に戻す
        sql = """
            UPDATE node_commands 
            SET val_status = %s, log_msg = %s, log_code = %s, val_res_payload = %s, completed_at = NOW(3) 
            WHERE id = %s
        """
        try:
            return self.execute(sql, (final_status, log_msg, log_code, res_json, cmd_id))
        except Exception as e:
            logger.error(f"Finalize SQL Error: {e}")
            return False