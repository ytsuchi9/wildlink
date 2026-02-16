import mysql.connector
import os
from dotenv import load_dotenv
from datetime import datetime

class DBBridge:
    def __init__(self, dotenv_path=None):
        # 1. パス解決: hub_managerから呼ばれた際、共通の.envを確実に探す
        if dotenv_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # /opt/wildlink/common -> /opt/wildlink/.env
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
        """
        Hub Managerが受信したレスポンスをDBに反映する (新規追加)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            now = datetime.now()

            # 1. node_commands のタイムスタンプ更新
            if "cmd_id" in payload:
                cmd_id = payload["cmd_id"]
                val_status = payload.get("val_status", "success")
                
                # 最初の返信ならacked_at、完了ならcompleted_atを埋める
                sql = """
                    UPDATE node_commands 
                    SET val_status = %s, 
                        acked_at = IFNULL(acked_at, %s),
                        completed_at = CASE WHEN %s = 'success' THEN %s ELSE completed_at END
                    WHERE id = %s
                """
                cursor.execute(sql, (val_status, now, val_status, now, cmd_id))

            # 2. 必要に応じて node_status テーブル等に最新の env_ や sys_ を保存する
            # (将来的な肉付けポイント)

            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[DBBridge] update_node_status Error: {e}")
            return False

    def fetch_node_config(self, node_id):
        """ノードの構成情報を取得する"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            # 仕様書の sys_id 命名に合わせて検索
            query = """
                SELECT c.vst_type, c.val_params, cat.vst_class, cat.vst_module
                FROM node_configs c
                JOIN device_catalog cat ON c.vst_type = cat.vst_type
                WHERE c.sys_id = %s AND c.val_enabled = TRUE
            """
            cursor.execute(query, (node_id,))
            configs = cursor.fetchall()
            cursor.close()
            conn.close()
            return configs
        except Exception as e:
            print(f"[DBBridge] Fetch Error: {e}")
            return None

    def save_log(self, sql, params):
        """ログを保存する"""
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