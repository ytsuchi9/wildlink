import mysql.connector
import os
import json # 追加
from dotenv import load_dotenv
from datetime import datetime

class DBBridge:
    def __init__(self, dotenv_path=None):
        # 1. パス解決: 既存ロジック維持
        if dotenv_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
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
        # 既存ロジック維持
        if not self.host:
            raise ValueError("DBBridge Error: Host is not defined. Check .env path.")
        return mysql.connector.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            connect_timeout=5
        )

    def update_node_status(self, node_id, payload):
        # 既存のコマンド更新ロジック（そのまま維持）
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

            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[DBBridge] update_node_status Error: {e}")
            return False

    def fetch_node_config(self, node_id):
        """ノードの構成情報を取得し、JSONを辞書にパースして返す"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            # JOIN済みのクエリ
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

            # ここで val_params を JSON文字列から Python辞書に変換しておく
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

    def save_log(self, sql, params):
        # 既存ロジック維持
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[DBBridge] Save Error: {e}")
            return False

    def _execute(self, sql, params=None):
        """UPDATE/INSERT/DELETE などの実行用汎用メソッド"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, params or ())
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[DBBridge] Execute Error: {e}")
            return False

    # --- 私が追加をお願いしたメソッドの「execute_query」を「_execute」に書き換え ---

    def update_node_heartbeat(self, sys_id, status="online"):
        query = "UPDATE nodes SET sys_status = %s, last_seen = NOW() WHERE sys_id = %s"
        # self.execute_query ではなく self._execute を使う
        return self._execute(query, (status, sys_id))

    def update_command_status(self, cmd_id, status="acked"):
        # node_commandsテーブルの主キーが id なのか command_id なのかは要確認
        # update_node_statusメソッド内では WHERE id = %s となっています
        column = "acked_at" if status == "acked" else "completed_at"
        query = f"UPDATE node_commands SET {column} = NOW() WHERE id = %s"
        return self._execute(query, (cmd_id,))