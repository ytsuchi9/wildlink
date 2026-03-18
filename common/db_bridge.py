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

    def _execute(self, sql, params=None):
        """汎用実行メソッド"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(buffered=True)
            cursor.execute(sql, params or ())
            # autocommit=Trueだが明示的にcommit（DDL等への配慮）
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

    # --- ログ管理機能 ---
    def insert_system_log(self, sys_id, log_type, level, msg, code=0, ext=None):
        """system_logsテーブルへログを保存"""
        sql = """
            INSERT INTO system_logs (sys_id, log_type, log_level, log_msg, log_code, log_ext)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        return self._execute(sql, (sys_id, log_type, level, msg, code, ext))

    def get_log_level(self, sys_id):
        """nodesテーブルから設定されたログレベルを取得 (有効なレコードのみ)"""
        sql = "SELECT val_log_level FROM nodes WHERE sys_id = %s AND is_active = 1"
        row = self.fetch_one(sql, (sys_id,))
        return row[0] if row else "info"

    # --- ステータス・ハートビート管理 ---
    def update_node_heartbeat(self, sys_id, status="online"):
        """生存報告。updated_at を現在時刻に更新 (旧last_seen)"""
        query = "UPDATE nodes SET sys_status = %s, updated_at = NOW() WHERE sys_id = %s AND is_active = 1"
        return self._execute(query, (status, sys_id))

    def update_vst_status(self, sys_id, vst_role_name, status, val_params=None):
        """
        node_status_current を更新。最新の『今の顔』をキャッシュする。
        vst_typeではなく vst_role_name を主軸に管理。
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            params_json = json.dumps(val_params) if val_params else None
            
            # 役割名(vst_role_name)をキーにして更新
            query = """
                INSERT INTO node_status_current (sys_id, vst_role_name, val_status, val_params, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE 
                    val_status = VALUES(val_status),
                    val_params = VALUES(val_params),
                    updated_at = NOW()
            """
            cursor.execute(query, (sys_id, vst_role_name, status, params_json))
            cursor.close()
            return True
        except Exception as e:
            print(f"[DBBridge] update_vst_status Error: {e}")
            return False

    # --- 構成情報取得 (履歴保持対応) ---
    def fetch_node_config(self, sys_id):
        """指定された sys_id の有効(is_active=1)なプラグイン構成を全取得"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            # is_active = 1 の最新設定のみをJOIN
            query = """
                SELECT c.vst_type, c.val_params, c.is_active, c.vst_role_name, 
                       c.hw_driver, c.hw_bus_addr, c.val_unit_map,
                       cat.vst_class, cat.vst_module
                FROM node_configs c
                JOIN device_catalog cat ON c.vst_type = cat.vst_type
                WHERE c.sys_id = %s AND c.is_active = 1 AND cat.is_active = 1
            """
            cursor.execute(query, (sys_id,))
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
            print(f"[DBBridge] fetch_node_config Error: {e}")
            return None

    def save_node_config(self, sys_id, vst_role_name, vst_type, val_params):
        """
        重要：設定を履歴保持型で保存する。
        1. 既存の同一Roleの設定を is_active=0 に。
        2. 新しい設定を is_active=1 で INSERT。
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 1. 旧設定を無効化
            deactivate_sql = "UPDATE node_configs SET is_active = 0 WHERE sys_id = %s AND vst_role_name = %s"
            cursor.execute(deactivate_sql, (sys_id, vst_role_name))
            
            # 2. 新設定を挿入
            params_json = json.dumps(val_params) if isinstance(val_params, dict) else val_params
            insert_sql = """
                INSERT INTO node_configs (sys_id, vst_role_name, vst_type, val_params, is_active, created_at)
                VALUES (%s, %s, %s, %s, 1, NOW())
            """
            cursor.execute(insert_sql, (sys_id, vst_role_name, vst_type, params_json))
            
            cursor.close()
            return True
        except Exception as e:
            print(f"[DBBridge] save_node_config Error: {e}")
            return False

    def fetch_vst_links(self, sys_id):
        """連動設定を取得 (is_active=1のみ)"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT source_role, target_role, event_type, action_cmd, action_params, val_interval 
                FROM vst_links 
                WHERE sys_id = %s AND is_active = 1
            """
            cursor.execute(query, (sys_id,))
            links = cursor.fetchall()
            cursor.close()
            
            for link in links:
                if link.get('action_params') and isinstance(link['action_params'], str):
                    try:
                        link['action_params'] = json.loads(link['action_params'])
                    except: pass
            return links
        except Exception as e:
            print(f"[DBBridge] fetch_vst_links Error: {e}")
            return []

    # --- データ蓄積 ---
    def insert_node_data(self, sys_id, vst_role_name, data_dict, raw_json=None):
        """
        node_data テーブルへセンサー値を保存 (ハイブリッド型)
        """
        sql = """
            INSERT INTO node_data (sys_id, vst_role_name, env_temp, env_hum, env_pres, env_lux, raw_data, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """
        params = (
            sys_id,
            vst_role_name,
            data_dict.get('temp'),
            data_dict.get('hum'),
            data_dict.get('pres'),
            data_dict.get('lux'),
            raw_json or json.dumps(data_dict)
        )
        return self._execute(sql, params)

    # --- コマンド管理 (既存のタイムスタンプ設計を維持) ---
    def update_node_status(self, sys_id, payload):
        """node_commands 履歴更新"""
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
                    WHERE id = %s AND sys_id = %s
                """
                cursor.execute(sql, (val_status, now, val_status, now, cmd_id, sys_id))
            cursor.close()
            return True
        except Exception as e:
            print(f"[DBBridge] update_node_status Error: {e}")
            return False

    def fetch_pending_commands(self, sys_id=None):
        """実行待ちコマンドを取得"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM node_commands WHERE val_status = 'pending'"
            params = []
            if sys_id:
                query += " AND sys_id = %s"
                params.append(sys_id)
            cursor.execute(query, params)
            result = cursor.fetchall()
            cursor.close()
            return result
        except Exception as e:
            print(f"[DBBridge] fetch_pending_commands Error: {e}")
            return []

    def update_command_status(self, cmd_id, status):
        """コマンドの状態遷移を記録"""
        column_update = ""
        if status == "sent": column_update = ", sent_at = NOW(3)"
        elif status == "acked": column_update = ", acked_at = NOW(3)"
        elif status == "completed": column_update = ", completed_at = NOW(3)"
        query = f"UPDATE node_commands SET val_status = %s {column_update} WHERE id = %s"
        return self._execute(query, (status, cmd_id))