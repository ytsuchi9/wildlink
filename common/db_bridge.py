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
    # 1. コンソール出力用
    stream_handler = logging.StreamHandler()
    
    # 2. ファイル出力用 (プロジェクトルートの logs/db_error.log に保存)
    log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "db_error.log")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    file_handler = logging.FileHandler(log_file)
    
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s - %(message)s')
    stream_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    
    db_logger.addHandler(stream_handler)
    db_logger.addHandler(file_handler)
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
        """辞書・リスト型が含まれる場合は自動でJSON文字列化します。"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(buffered=True)
            
            # 🌟 修正: パラメータの無害化（シリアライズ）
            safe_params = []
            if params:
                for p in params:
                    # 辞書型またはリスト型ならJSON文字列に変換
                    if isinstance(p, (dict, list)):
                        safe_params.append(json.dumps(p, ensure_ascii=False))
                    # Boolean型はMySQLのTINYINT(1/0)に合わせて変換
                    elif isinstance(p, bool):
                        safe_params.append(1 if p else 0)
                    else:
                        safe_params.append(p)

            cursor.execute(sql, tuple(safe_params) if safe_params else ())
            
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

    def execute_logic(self, data):
        """
        WES 2026 準拠: 設定パッチの動的適用と log_ext による全状態報告
        """
        try:
            # 1. パッチの適用 (cmd_jsonの内容を自身の属性へ自動反映)
            # data に含まれるキーのうち、規約(val_, act_)に合致するもののみを上書き
            updated_keys = []
            for key, value in data.items():
                if hasattr(self, key) and key.startswith(('val_', 'act_')):
                    # 型の整合性を保つための簡易変換 (1/0 -> True/False)
                    if isinstance(getattr(self, key), bool) and not isinstance(value, bool):
                        value = (int(value) == 1)
                    
                    setattr(self, key, value)
                    updated_keys.append(key)

            logger.info(f"⚙️ [{self.role}] Patched: {', '.join(updated_keys)}")

            # 2. 現在の全パラメータを抽出 (データの器：log_ext の生成)
            # 自身の属性から val_, act_, env_ で始まるものを全て集める
            current_params = {
                k: v for k, v in vars(self).items() 
                if k.startswith(('val_', 'act_', 'env_'))
            }

            # 3. 完了報告 (Hub側のDB: node_configs と node_status_current を同時に更新させる)
            self.send_response(
                "completed", 
                log_msg=f"Configuration patched: {', '.join(updated_keys)}",
                log_code=200,
                log_ext=current_params # これがそのままDBの全項目を同期する「器」になる
            )

            return True 

        except Exception as e:
            logger.error(f"❌ Error in execute_logic: {e}")
            self.send_response("error", log_msg=str(e), log_code=500)
            return Falsesg, code, ext_json

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

    def insert_node_data(self, sys_id, vst_role_name, payload):
        """
        センサー等の測定値や検知履歴を node_data テーブルに保存します。
        マニフェストの命名規則 (env_, log_msg) に従いペイロードから抽出します。
        """
        # 環境データがあれば抽出（今回は動体検知なので None になる想定）
        env_temp = payload.get('env_temp')
        env_hum = payload.get('env_hum')
        env_pres = payload.get('env_pres')
        env_lux = payload.get('env_lux')
        
        # ログメッセージと生データ(JSON)
        log_msg = payload.get('log_msg', f"Data recorded from {vst_role_name}")
        raw_data_json = json.dumps(payload, ensure_ascii=False)

        sql = """
            INSERT INTO node_data 
            (sys_id, vst_role_name, env_temp, env_hum, env_pres, env_lux, log_msg, raw_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        return self.execute(sql, (
            sys_id, vst_role_name, 
            env_temp, env_hum, env_pres, env_lux, 
            log_msg, raw_data_json
        ))

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

    def update_vst_configs(self, sys_id, role, config_dict):
        """
        node_configsテーブルを動的に更新。
        - val_enabled はカラムへ直接。
        - その他(val_interval等)は val_params(JSON) 内へ保存。
        """
        if not config_dict or not isinstance(config_dict, dict):
            return True

        # 1. データの仕分け
        direct_columns = {}  # 実際の物理カラム用
        json_params = {}     # val_params(JSON)用
        
        # 物理カラムとして存在する項目
        KNOWN_COLUMNS = ['val_enabled'] 

        def sort_params(d):
            for k, v in d.items():
                if k.startswith(('val_', 'act_')):
                    if k in ['val_status', 'val_paused']: continue # 状態値は除外
                    
                    if k in KNOWN_COLUMNS:
                        direct_columns[k] = v
                    else:
                        json_params[k] = v
                elif isinstance(v, dict):
                    sort_params(v)

        sort_params(config_dict)

        try:
            sql_parts = []
            vals = []

            # A. 物理カラムの更新
            for k, v in direct_columns.items():
                sql_parts.append(f"{k} = %s")
                vals.append(1 if v is True else (0 if v is False else v))

            # B. JSONカラム(val_params)の更新 (JSON_SETを使用)
            if json_params:
                # 既存値を壊さないよう JSON_SET(COALESCE(val_params, '{}'), ...)
                json_expr = "val_params = JSON_SET(COALESCE(val_params, '{}')"
                for k, v in json_params.items():
                    json_expr += f", '$.{k}', %s"
                    vals.append(1 if v is True else (0 if v is False else v))
                json_expr += ")"
                sql_parts.append(json_expr)

            if not sql_parts:
                return True

            # C. SQL組み立てと実行
            sql = f"UPDATE node_configs SET {', '.join(sql_parts)} WHERE sys_id = %s AND vst_role_name = %s"
            vals.extend([sys_id, role])

            # 🌟 ここで db_logger (db_bridge_safe) を使用
            db_logger.debug(f"⚙️ [DB] Syncing config for {role}: {sql} with {vals}")
            
            # self.execute 等、既存の実行メソッドを使用
            self.execute(sql, tuple(vals))
            return True

        except Exception as e:
            # 🌟 ここも db_logger を使用
            db_logger.error(f"❌ [DB] update_vst_configs failed: {e}")
            return False

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
        # acked_at がNULLになる場合はSQLに以下を追加
        # 🌟 acked_at = IFNULL(acked_at, NOW(3)) を追加
        sql = """
            UPDATE node_commands 
            SET val_status = %s, log_msg = %s, log_code = %s, val_res_payload = %s, completed_at = NOW(3) 
            WHERE id = %s
        """
        return self.execute(sql, (status, log_msg, log_code, res_json, cmd_id))