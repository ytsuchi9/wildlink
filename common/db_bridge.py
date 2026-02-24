import mysql.connector
import os
import json
from dotenv import load_dotenv
from datetime import datetime

class DBBridge:
    def __init__(self, dotenv_path=None):
        # 1. パス解決
        if dotenv_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # commonフォルダの親にある.envを参照
            dotenv_path = os.path.join(os.path.dirname(current_dir), ".env")
        
        load_dotenv(dotenv_path)
        
        # 2. 環境変数の取得
        self.host = os.getenv('DB_HOST') or os.getenv('MQTT_BROKER')
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASS')
        self.database = os.getenv('DB_NAME')
        
        if self.host is None:
             print(f"[DBBridge] ⚠️ WARNING: Host is None. Path: {dotenv_path}")

    def _get_connection(self):
        """データベース接続を確立（タイムアウト5秒設定）"""
        if not self.host:
            raise ValueError("DBBridge Error: Host is not defined. Check .env path.")
        
        # 毎回新しいコネクションを作成（Lost Connection対策）
        return mysql.connector.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            connect_timeout=5,
            autocommit=True
        )

    def fetch_node_config(self, node_id):
        """ノードの構成情報を取得し、JSONを辞書に変換して返す"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT c.vst_type, c.val_params, c.val_enabled, cat.vst_class, cat.vst_module
                FROM node_configs c
                JOIN device_catalog cat ON c.vst_type = cat.vst_type
                WHERE c.sys_id = %s AND c.val_enabled = TRUE
            """
            cursor.execute(query, (node_id,))
            configs = cursor.fetchall()
            
            cursor.close()
            conn.close()

            # val_params(JSON文字列) を Python辞書に変換
            for cfg in configs:
                if cfg['val_params'] and isinstance(cfg['val_params'], str):
                    try:
                        cfg['val_params'] = json.loads(cfg['val_params'])
                    except json.JSONDecodeError:
                        print(f"[DBBridge] ⚠️ JSON Decode Error for {cfg['vst_type']}")
            
            return configs
        except Exception as e:
            print(f"[DBBridge] Fetch Error: {e}")
            return None

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
        """汎用ログ保存"""
        return self._execute(sql, params)

    def _execute(self, sql, params=None):
        """UPDATE/INSERT/DELETE 実行用汎用メソッド"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, params or ())
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[DBBridge] Execute Error: {e}")
            return False

    def update_node_heartbeat(self, sys_id, status="online"):
        """生存報告（Heartbeat）の更新"""
        query = "UPDATE nodes SET sys_status = %s, last_seen = NOW() WHERE sys_id = %s"
        return self._execute(query, (status, sys_id))

    def update_command_status(self, cmd_id, status="acked"):
        """コマンドの受諾/完了時刻の更新"""
        column = "acked_at" if status == "acked" else "completed_at"
        query = f"UPDATE node_commands SET {column} = NOW() WHERE id = %s"
        return self._execute(query, (cmd_id,))