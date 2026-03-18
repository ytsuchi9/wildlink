🛠️ WildLink 2026 Role-Based 仕様定義 (Draft)

1. 設計コンセプト従来の「デバイス種別（vst_type）」による一律管理から、「役割（vst_role_name）」を主軸とした柔軟な制御へ移行する。
vst_type: デバイスの物理的・機能的な分類（camera, sensor, switch）。JOINやUIコンポーネントの決定に使用。vst_role_name: システム内での固有の役割名（cam_main, cam_sub, sns_move）。コマンドの宛先、MQTTトピック、HTMLのIDに使用。

2. データベース構造（整合性確定版）
① node_configs (構成情報)カラム名型説明vst_typeVARCHARcamera, sensor 等の種別（device_catalogと結合）vst_role_nameVARCHARcam_main, cam_sub 等の固有IDis_activeTINYINT有効フラグ（履歴保持のため 1 のものを使用）
② node_status_current (動的ステータス)カラム名型説明sys_idVARCHARノードIDvst_role_nameVARCHAR役割名（UNIQUE INDEX: sys_id + role）val_statusVARCHARidle, streaming, detected 等の現在の状態updated_atTIMESTAMP最終更新時間（フロントエンドの死活監視に使用）
③ node_commands (コマンド制御)カラム名型説明vst_role_nameVARCHAR実行対象の役割名val_statusVARCHARpending → sent → success / errorval_res_payloadLONGTEXT実行結果（JSON）。ストリームURL等を格納log_codeINT実行結果コード（0:正常, その他:エラー）
④ system_logs (イベント履歴)カラム名型説明ext_infoTEXT(旧 log_ext)。JSON形式の拡張データやセンサー生値log_codeINTイベント/エラーコード


DB構造

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
| val_log_level | varchar(20)   | YES  |     | info                |                               |
| val_ui_layout | longtext      | YES  |     | NULL                |                               |
| log_note      | text          | YES  |     | NULL                |                               |
| is_active     | tinyint(1)    | YES  |     | 1                   |                               |
| created_at    | timestamp     | YES  |     | current_timestamp() |                               |
| updated_at    | timestamp     | YES  |     | current_timestamp() | on update current_timestamp() |
+---------------+---------------+------+-----+---------------------+-------------------------------+
14 rows in set (0.006 sec)

MariaDB [wildlink_db]> SHOW COLUMNS FROM device_catalog;
+-------------------+--------------+------+-----+---------------------+-------------------------------+
| Field             | Type         | Null | Key | Default             | Extra                         |
+-------------------+--------------+------+-----+---------------------+-------------------------------+
| vst_type          | varchar(50)  | NO   | PRI | NULL                |                               |
| vst_class         | varchar(100) | YES  |     | NULL                |                               |
| ui_component_type | varchar(30)  | YES  |     | NULL                |                               |
| vst_module        | varchar(100) | YES  |     | NULL                |                               |
| default_params    | longtext     | YES  |     | NULL                |                               |
| log_note          | text         | YES  |     | NULL                |                               |
| is_active         | tinyint(1)   | YES  |     | 1                   |                               |
| created_at        | timestamp    | YES  |     | current_timestamp() |                               |
| updated_at        | timestamp    | YES  |     | current_timestamp() | on update current_timestamp() |
+-------------------+--------------+------+-----+---------------------+-------------------------------+
9 rows in set (0.006 sec)

MariaDB [wildlink_db]> SHOW COLUMNS FROM node_configs;
+-----------------+--------------+------+-----+---------+----------------+
| Field           | Type         | Null | Key | Default | Extra          |
+-----------------+--------------+------+-----+---------+----------------+
| config_id       | int(11)      | NO   | PRI | NULL    | auto_increment |
| sys_id          | varchar(50)  | YES  | MUL | NULL    |                |
| vst_type        | varchar(50)  | YES  | MUL | NULL    |                |
| vst_role_name   | varchar(100) | YES  |     | NULL    |                |
| is_active       | tinyint(1)   | YES  |     | 1       |                |
| vst_description | text         | YES  |     | NULL    |                |
| val_unit_map    | longtext     | YES  |     | NULL    |                |
| hw_driver       | varchar(50)  | YES  |     | NULL    |                |
| hw_bus_addr     | varchar(20)  | YES  |     | NULL    |                |
| val_params      | longtext     | YES  |     | NULL    |                |
| val_enabled     | tinyint(1)   | YES  |     | 1       |                |
+-----------------+--------------+------+-----+---------+----------------+
11 rows in set (0.005 sec)

MariaDB [wildlink_db]> SHOW COLUMNS FROM node_commands;
+-----------------+--------------+------+-----+----------------------+----------------+
| Field           | Type         | Null | Key | Default              | Extra          |
+-----------------+--------------+------+-----+----------------------+----------------+
| id              | int(11)      | NO   | PRI | NULL                 | auto_increment |
| sys_id          | varchar(50)  | NO   | MUL | NULL                 |                |
| vst_role_name   | varchar(50)  | YES  |     | NULL                 |                |
| cmd_type        | varchar(50)  | YES  |     | NULL                 |                |
| cmd_json        | longtext     | YES  |     | NULL                 |                |
| val_status      | varchar(20)  | YES  | MUL | pending              |                |
| log_code        | varchar(30)  | YES  | MUL | NULL                 |                |
| log_msg         | text         | YES  |     | NULL                 |                |
| val_res_payload | longtext     | YES  |     | NULL                 |                |
| created_at      | timestamp(3) | YES  |     | current_timestamp(3) |                |
| sent_at         | timestamp(3) | YES  |     | NULL                 |                |
| acked_at        | timestamp(3) | YES  |     | NULL                 |                |
| completed_at    | timestamp(3) | YES  |     | NULL                 |                |
+-----------------+--------------+------+-----+----------------------+----------------+
13 rows in set (0.006 sec)

MariaDB [wildlink_db]> SHOW COLUMNS FROM node_status_current;
+---------------+-------------+------+-----+---------------------+-------------------------------+
| Field         | Type        | Null | Key | Default             | Extra                         |
+---------------+-------------+------+-----+---------------------+-------------------------------+
| sys_id        | varchar(50) | NO   | PRI | NULL                |                               |
| vst_role_name | varchar(50) | NO   | PRI | NULL                |                               |
| val_status    | varchar(20) | YES  |     | idle                |                               |
| val_params    | longtext    | YES  |     | NULL                |                               |
| updated_at    | datetime    | YES  |     | current_timestamp() | on update current_timestamp() |
+---------------+-------------+------+-----+---------------------+-------------------------------+
5 rows in set (0.006 sec)

MariaDB [wildlink_db]> SHOW COLUMNS FROM vst_links;
+---------------+-------------+------+-----+---------------------+-------------------------------+
| Field         | Type        | Null | Key | Default             | Extra                         |
+---------------+-------------+------+-----+---------------------+-------------------------------+
| id            | int(11)     | NO   | PRI | NULL                | auto_increment                |
| sys_id        | varchar(50) | NO   |     | NULL                |                               |
| source_role   | varchar(50) | NO   |     | NULL                |                               |
| target_role   | varchar(50) | NO   |     | NULL                |                               |
| event_type    | varchar(50) | YES  |     | any                 |                               |
| action_cmd    | varchar(50) | YES  |     | NULL                |                               |
| action_params | longtext    | YES  |     | NULL                |                               |
| val_interval  | int(11)     | YES  |     | 30                  |                               |
| is_active     | tinyint(1)  | YES  |     | 1                   |                               |
| created_at    | timestamp   | YES  |     | current_timestamp() |                               |
| updated_at    | timestamp   | YES  |     | current_timestamp() | on update current_timestamp() |
+---------------+-------------+------+-----+---------------------+-------------------------------+
11 rows in set (0.005 sec)

MariaDB [wildlink_db]> SHOW COLUMNS FROM node_data;
+---------------+-------------+------+-----+---------------------+----------------+
| Field         | Type        | Null | Key | Default             | Extra          |
+---------------+-------------+------+-----+---------------------+----------------+
| id            | int(11)     | NO   | PRI | NULL                | auto_increment |
| sys_id        | varchar(50) | NO   |     | NULL                |                |
| vst_role_name | varchar(50) | YES  |     | NULL                |                |
| env_temp      | float       | YES  |     | NULL                |                |
| env_hum       | float       | YES  |     | NULL                |                |
| env_pres      | float       | YES  |     | NULL                |                |
| env_lux       | float       | YES  |     | NULL                |                |
| log_msg       | text        | YES  |     | NULL                |                |
| raw_data      | longtext    | YES  |     | NULL                |                |
| created_at    | timestamp   | YES  |     | current_timestamp() |                |
+---------------+-------------+------+-----+---------------------+----------------+
10 rows in set (0.005 sec)

MariaDB [wildlink_db]> SHOW COLUMNS FROM system_logs;
+-------------+-------------+------+-----+---------------------+----------------+
| Field       | Type        | Null | Key | Default             | Extra          |
+-------------+-------------+------+-----+---------------------+----------------+
| id          | int(11)     | NO   | PRI | NULL                | auto_increment |
| sys_id      | varchar(50) | YES  | MUL | NULL                |                |
| log_type    | varchar(50) | YES  |     | NULL                |                |
| log_level   | varchar(20) | YES  |     | info                |                |
| log_code    | int(11)     | YES  |     | 0                   |                |
| sys_volt    | float       | YES  |     | NULL                |                |
| sys_cpu_t   | float       | YES  |     | NULL                |                |
| sys_board_t | float       | YES  |     | NULL                |                |
| net_rssi    | float       | YES  |     | NULL                |                |
| sys_up      | int(11)     | YES  |     | NULL                |                |
| log_msg     | text        | YES  |     | NULL                |                |
| ext_info    | text        | YES  |     | NULL                |                |
| created_at  | timestamp   | YES  |     | current_timestamp() |                |
| log_ext     | longtext    | YES  |     | NULL                |                |
+-------------+-------------+------+-----+---------------------+----------------+