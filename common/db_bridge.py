import mysql.connector
import os
from dotenv import load_dotenv

class DBBridge:
    def __init__(self, dotenv_path=None):
        # 1. すでに os.environ に値があるかチェック。なければロード。
        if not os.getenv('DB_USER') and dotenv_path:
            load_dotenv(dotenv_path)
        
        # 2. 直接環境変数から取得（Noneなら空文字にするなどガード）
        self.host = os.getenv('DB_HOST') or os.getenv('MQTT_BROKER')
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASS')
        self.database = os.getenv('DB_NAME')
        
        # デバッグ用（この段階で None になっていないか確認）
        if self.host is None:
            print(f"[DBBridge Internal DEBUG] HOST IS NONE! ENV_DB_HOST: {os.getenv('DB_HOST')}, ENV_MQTT: {os.getenv('MQTT_BROKER')}")

    def _get_connection(self):
        # もし万が一 None ならここでエラーを出して止める
        if not self.host:
            raise ValueError("DBBridge Error: Host is not defined. Check your .env file path.")
            
        return mysql.connector.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            connect_timeout=5  # タイムアウトを短くして原因を早く特定
        )

    def fetch_node_config(self, node_id):
        """ノードの構成情報を取得する土管"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
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
        """ログを保存する土管 (Hub用)"""
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