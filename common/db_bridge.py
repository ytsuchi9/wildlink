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
        
        if self.host is None:
             print(f"[DBBridge] ⚠️ WARNING: Host is None. Path: {dotenv_path}")

    def _get_connection(self):
        if not self.host:
            raise ValueError("DBBridge Error: Host is not defined. Check .env path.")
        
        return mysql.connector.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            connect_timeout=5,
            autocommit=True
        )

    def fetch_node_config(self, node_id):
        """ノードの構成情報を取得し、新設計カラム(hw_driver等)を含めて返す"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            # 💡 修正ポイント: SQLに新カラムを追加！
            query = """
                SELECT 
                    c.vst_type, 
                    c.val_params, 
                    c.val_enabled, 
                    c.vst_role_name, 
                    c.hw_driver, 
                    c.hw_bus_addr, 
                    c.val_unit_map,
                    cat.vst_class, 
                    cat.vst_module
                FROM node_configs c
                JOIN device_catalog cat ON c.vst_type = cat.vst_type
                WHERE c.sys_id = %s AND c.val_enabled = TRUE
            """
            cursor.execute(query, (node_id,))
            configs = cursor.fetchall()
            
            cursor.close()
            conn.close()

            # JSON文字列を Python辞書にデコード
            for cfg in configs:
                # val_params のデコード
                if cfg.get('val_params') and isinstance(cfg['val_params'], str):
                    try:
                        cfg['val_params'] = json.loads(cfg['val_params'])
                    except json.JSONDecodeError:
                        print(f"[DBBridge] ⚠️ JSON Decode Error (params) for {cfg['vst_type']}")
                
                # val_unit_map のデコード (新設計)
                if cfg.get('val_unit_map') and isinstance(cfg['val_unit_map'], str):
                    try:
                        cfg['val_unit_map'] = json.loads(cfg['val_unit_map'])
                    except json.JSONDecodeError:
                        print(f"[DBBridge] ⚠️ JSON Decode Error (unit_map) for {cfg['vst_type']}")
            
            return configs
        except Exception as e:
            print(f"[DBBridge] Fetch Error: {e}")
            return None

    def fetch_vst_links(self, node_id):
        """ノードに関連するイベントリンク情報を取得（有効なもののみ）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            # val_enabled = 1 のものだけを抽出して「隠しレコード」を無視
            query = """
                SELECT source_role, target_role, event_type, val_interval 
                FROM vst_links 
                WHERE sys_id = %s AND val_enabled = 1
            """
            cursor.execute(query, (node_id,))
            links = cursor.fetchall()
            
            cursor.close()
            conn.close()
            return links
        except Exception as e:
            print(f"[DBBridge] Link Fetch Error: {e}")
            return []

    # --- 以下、変更なしのためメソッド名のみ維持（そのまま使ってください） ---

    def update_node_status(self, node_id, payload):
        """コマンド実行状態の更新（既存ロジック）"""
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
            conn.close()
            return True
        except Exception as e:
            print(f"[DBBridge] update_node_status Error: {e}")
            return False

    def save_log(self, sql, params):
        return self._execute(sql, params)

    def _execute(self, sql, params=None):
        try:
            conn = self._get_connection()
            cursor = conn.cursor(buffered=True) 
            cursor.execute(sql, params or ())
            if cursor.with_rows:
                cursor.fetchall()
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[DBBridge] Execute Error: {e} | SQL: {sql[:50]}...")
            return False

    def fetch_one(self, sql, params=None):
        try:
            conn = self._get_connection()
            cursor = conn.cursor(buffered=True)
            cursor.execute(sql, params or ())
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            return result
        except Exception as e:
            print(f"[DBBridge] FetchOne Error: {e}")
            return None

    def update_node_heartbeat(self, sys_id, status="online"):
        query = "UPDATE nodes SET sys_status = %s, last_seen = NOW() WHERE sys_id = %s"
        return self._execute(query, (status, sys_id))

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
            conn.close()
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