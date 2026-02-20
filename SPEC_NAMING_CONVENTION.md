WildLink Project 命名規則 & 連携仕様書
1. 変数・カラム接頭語（プレフィックス）すべての項目は、以下の意味を持つ接頭語から始め、すべて小文字とする。
接頭語  意味    項目例
hw_     物理固定 / ハードウェア設定     hw_pin, hw_driver, hw_bus, hw_pwr_src
val_    動作設定 / 状態                val_name, val_enabled, val_status, val_interval
act_    発動条件 / 制御コマンド         act_line, act_rec, act_strobe
env_    測定データ (環境)               env_temp, env_hum, env_pres, env_lux
sys_    本体状態 (システム)             sys_id, sys_cpu_t, sys_volt, sys_up, sys_status
log_    記録 / 履歴 / メッセージ        log_level, log_msg, log_code, log_note
net_    通信関連                        net_ssid, net_rssi, net_ip
loc_    位置情報                    loc_lat, loc_lon, loc_name

2. データベース連携（node_commands テーブル）
WebからNodeへ命令を送る際の標準フォーマット。
cmd_type: 命令の種類を入れる（例: stream_start, stream_stop, sensor_start）
cmd_json: 追加引数が必要な場合にJSON形式で格納
val_status 遷移:
    pending: Webが発行（初期値）
    sent: ブリッジ/PHPがMQTTへ送出
    success: Nodeが実行完了を報告
    error: 実行失敗（内容は log_msg へ）
    
3. ファイル構造と役割
.env: パスワード等の秘匿情報（/opt/wildlink/.env）
db_config.php: PHPからのDB接続を一元管理（一つ上の .env を参照）
main_manager.py: Node側のメイン。MQTTで cmd_type を受け取り各VSTへ振り分け。

4. データベースの構造
MariaDB [wildlink_db]> SHOW TABLES;
+-----------------------+
| Tables_in_wildlink_db |
+-----------------------+
| device_catalog        |
| node_commands         |
| node_configs          |
| node_data             |
| nodes                 |
| system_logs           |
+-----------------------+

MariaDB [wildlink_db]> SHOW COLUMNS FROM device_catalog;
+----------------+--------------+------+-----+---------+-------+
| Field          | Type         | Null | Key | Default | Extra |
+----------------+--------------+------+-----+---------+-------+
| vst_type       | varchar(50)  | NO   | PRI | NULL    |       |
| vst_class      | varchar(100) | YES  |     | NULL    |       |
| vst_module     | varchar(100) | YES  |     | NULL    |       |
| default_params | longtext     | YES  |     | NULL    |       |
| log_note       | text         | YES  |     | NULL    |       |
+----------------+--------------+------+-----+---------+-------+

MariaDB [wildlink_db]> SHOW COLUMNS FROM node_commands;
+--------------+--------------+------+-----+----------------------+----------------+
| Field        | Type         | Null | Key | Default              | Extra          |
+--------------+--------------+------+-----+----------------------+----------------+
| id           | int(11)      | NO   | PRI | NULL                 | auto_increment |
| sys_id       | varchar(50)  | NO   | MUL | NULL                 |                |
| cmd_type     | varchar(50)  | YES  |     | NULL                 |                |
| cmd_json     | longtext     | YES  |     | NULL                 |                |
| val_status   | varchar(20)  | YES  | MUL | pending              |                |
| log_msg      | text         | YES  |     | NULL                 |                |
| created_at   | timestamp(3) | YES  |     | current_timestamp(3) |                |
| sent_at      | timestamp(3) | YES  |     | NULL                 |                |
| acked_at     | timestamp(3) | YES  |     | NULL                 |                |
| completed_at | timestamp(3) | YES  |     | NULL                 |                |
+--------------+--------------+------+-----+----------------------+----------------+

MariaDB [wildlink_db]> SHOW COLUMNS FROM node_configs;
+-------------+-------------+------+-----+---------+----------------+
| Field       | Type        | Null | Key | Default | Extra          |
+-------------+-------------+------+-----+---------+----------------+
| config_id   | int(11)     | NO   | PRI | NULL    | auto_increment |
| sys_id      | varchar(50) | YES  | MUL | NULL    |                |
| vst_type    | varchar(50) | YES  | MUL | NULL    |                |
| val_params  | longtext    | YES  |     | NULL    |                |
| val_enabled | tinyint(1)  | YES  |     | 1       |                |
+-------------+-------------+------+-----+---------+----------------+

MariaDB [wildlink_db]> SHOW COLUMNS FROM node_data;
+------------+-------------+------+-----+---------------------+----------------+
| Field      | Type        | Null | Key | Default             | Extra          |
+------------+-------------+------+-----+---------------------+----------------+
| id         | int(11)     | NO   | PRI | NULL                | auto_increment |
| sys_id     | varchar(50) | NO   |     | NULL                |                |
| sys_cpu_t  | float       | YES  |     | NULL                |                |
| sys_volt   | float       | YES  |     | NULL                |                |
| env_temp   | float       | YES  |     | NULL                |                |
| env_hum    | float       | YES  |     | NULL                |                |
| env_pres   | float       | YES  |     | NULL                |                |
| env_lux    | float       | YES  |     | NULL                |                |
| log_msg    | text        | YES  |     | NULL                |                |
| raw_data   | longtext    | YES  |     | NULL                |                |
| created_at | timestamp   | YES  |     | current_timestamp() |                |
+------------+-------------+------+-----+---------------------+----------------+

MariaDB [wildlink_db]> SHOW COLUMNS FROM nodes;
+---------------+---------------+------+-----+---------------------+-------------------------------+
| Field         | Type          | Null | Key | Default             | Extra                         |
+---------------+---------------+------+-----+---------------------+-------------------------------+
| sys_id        | varchar(50)   | NO   | PRI | NULL                |                               |
| val_name      | varchar(100)  | YES  |     | NULL                |                               |
| loc_name      | varchar(100)  | YES  |     | NULL                |                               |
| loc_lat       | decimal(10,7) | YES  |     | NULL                |                               |
| loc_lon       | decimal(10,7) | YES  |     | NULL                |                               |
| hw_pwr_src    | varchar(20)   | YES  |     | NULL                |                               |
| net_ip        | varchar(15)   | YES  |     | NULL                |                               |
| sys_status    | varchar(20)   | YES  |     | NULL                |                               |
| val_ui_layout | longtext      | YES  |     | NULL                |                               |
| log_note      | text          | YES  |     | NULL                |                               |
| last_seen     | timestamp     | YES  |     | current_timestamp() | on update current_timestamp() |
+---------------+---------------+------+-----+---------------------+-------------------------------+

MariaDB [wildlink_db]> SHOW COLUMNS FROM system_logs;
+------------+-------------+------+-----+---------------------+----------------+
| Field      | Type        | Null | Key | Default             | Extra          |
+------------+-------------+------+-----+---------------------+----------------+
| id         | int(11)     | NO   | PRI | NULL                | auto_increment |
| sys_id     | varchar(50) | YES  | MUL | NULL                |                |
| log_level  | varchar(20) | YES  |     | info                |                |
| log_code   | int(11)     | YES  |     | 0                   |                |
| sys_volt   | float       | YES  |     | NULL                |                |
| sys_cpu_t  | float       | YES  |     | NULL                |                |
| net_rssi   | int(11)     | YES  |     | NULL                |                |
| sys_up     | int(11)     | YES  |     | NULL                |                |
| log_msg    | text        | YES  |     | NULL                |                |
| created_at | timestamp   | YES  |     | current_timestamp() |                |
+------------+-------------+------+-----+---------------------+----------------+
