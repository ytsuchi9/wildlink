1. ステータス専用テーブル node_status_current の導入（Hub側のみ）
このテーブルはHubのDBにだけ存在し、Nodeには同期しません。

Field,      Type,                           役割
sys_id,     varchar,    node_001
vst_type,   varchar,    cam_main
val_status, varchar,    streaming / idle
updated_at, datetime,                       最終更新（生存確認用）

・last_config.jsonはNODEが自分の設定を一時記憶している。
・node_status_currentはHUBがNODEの状態を一時記憶している

という考え方ですね！
動体センサやその他の動作状態を一目で見れるので便利だとおもいます。
これも定期的に監視して本当の状態なのかを監視するとさらによいかもですね



テーブル名,         役割,性格
device_catalog,     デバイスの辞書（SR501は人感、INA219は電力…）,静的 / 定義
node_configs,       「どのNodeに何を繋いだか」の構成図,動的 / 構成
vst_links,          「AがBならCせよ」という神経回路,動的 / 論理
node_status_current,        今、この瞬間の全ユニットの状態・計測値,リアルタイム / 現状
node_data,          過去の全計測値・ログのアーカイブ,蓄積 / 履歴



🚀 DBでUIプラグインを完全制御する設計案
現状の vst-manager.js を以下のようにアップグレードすることで、ソースコードを一切触らずに新しいセンサーに対応できるようになります。

2. 今後のコード修正の基準（データの住み分け）
DBを上記のように修正した後の、各テーブルへの書き込みルールを以下のように定義します。

カテゴリ,           テーブル,           カラム,                                     備考
システムバイタル,   system_logs,    "sys_cpu_t, sys_board_t, sys_volt, net_rssi",   定期報告で更新
コマンド結果,       node_commands,  "val_status, log_code, res_payload",            コマンドに対するレスポンス(Res)で更新
環境観測データ,     node_data,      "env_temp, env_hum, env_pres, env_lux",         センサー読み取り時のタイミングで更新

2. DB拡張への備忘録：log_note の活用
node_configs に「何のためのセンサーか」を書くカラムの追加ですが、既存の log_note カラムを暫定的に「表示用ラベル」として使い、動作確認後に正式な val_label カラム等を追加すれば、コードの破壊を防げます。


1. DBの node_configs テーブルにカラムを追加（将来）
例えば ui_plugin_file というカラムを追加し、そこに sensor-unit.js と書いておきます。


1. 推奨：機能ごとのファイル分割
HTML内に全てを書くのではなく、役割ごとにファイルを分けるのが最もクリーンです。

ファイル名,         役割
camviewer.html,     骨格（HTML）のみ。非常に短くなります。
vst-rack.css,       先ほどの「1Uデザイン」などのスタイル定義。
vst-manager.js,     "initRack, refreshStatus などの制御ロジック。"
vst-ui-parts.js,    createPluginUI などの描画ロジック（UIパーツ生成）。


1. フォルダ構成（再確認）
サーバー上の /var/www/html/ を以下の構成で配置。
/var/www/html/
├── camviewer.html
├── css/
│   └── vst-rack.css
└── js/
    ├── vst-manager.js     (全体の監視・同期)
    └── plugins/
        └── camera-unit.js (カメラ専用ロジック)


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
| last_seen     | timestamp     | YES  |     | current_timestamp() | on update current_timestamp() |
+---------------+---------------+------+-----+---------------------+-------------------------------+

MariaDB [wildlink_db]> SHOW COLUMNS FROM device_catalog;
+-------------------+--------------+------+-----+---------+-------+
| Field             | Type         | Null | Key | Default | Extra |
+-------------------+--------------+------+-----+---------+-------+
| vst_type          | varchar(50)  | NO   | PRI | NULL    |       |
| vst_class         | varchar(100) | YES  |     | NULL    |       |
| ui_component_type | varchar(30)  | YES  |     | NULL    |       |
| vst_module        | varchar(100) | YES  |     | NULL    |       |
| default_params    | longtext     | YES  |     | NULL    |       |
| log_note          | text         | YES  |     | NULL    |       |
+-------------------+--------------+------+-----+---------+-------+

MariaDB [wildlink_db]> SHOW COLUMNS FROM node_configs;
+-----------------+--------------+------+-----+---------+----------------+
| Field           | Type         | Null | Key | Default | Extra          |
+-----------------+--------------+------+-----+---------+----------------+
| config_id       | int(11)      | NO   | PRI | NULL    | auto_increment |
| sys_id          | varchar(50)  | YES  | MUL | NULL    |                |
| vst_type        | varchar(50)  | YES  | MUL | NULL    |                |
| vst_role_name   | varchar(100) | YES  |     | NULL    |                |
| vst_description | text         | YES  |     | NULL    |                |
| val_unit_map    | longtext     | YES  |     | NULL    |                |
| hw_driver       | varchar(50)  | YES  |     | NULL    |                |
| hw_bus_addr     | varchar(20)  | YES  |     | NULL    |                |
| val_params      | longtext     | YES  |     | NULL    |                |
| val_enabled     | tinyint(1)   | YES  |     | 1       |                |
+-----------------+--------------+------+-----+---------+----------------+

MariaDB [wildlink_db]> SHOW COLUMNS FROM node_commands;
+--------------+--------------+------+-----+----------------------+----------------+
| Field        | Type         | Null | Key | Default              | Extra          |
+--------------+--------------+------+-----+----------------------+----------------+
| id           | int(11)      | NO   | PRI | NULL                 | auto_increment |
| sys_id       | varchar(50)  | NO   | MUL | NULL                 |                |
| cmd_type     | varchar(50)  | YES  |     | NULL                 |                |
| cmd_json     | longtext     | YES  |     | NULL                 |                |
| val_status   | varchar(20)  | YES  | MUL | pending              |                |
| log_code     | varchar(30)  | YES  | MUL | NULL                 |                |
| log_msg      | text         | YES  |     | NULL                 |                |
| res_payload  | longtext     | YES  |     | NULL                 |                |
| created_at   | timestamp(3) | YES  |     | current_timestamp(3) |                |
| sent_at      | timestamp(3) | YES  |     | NULL                 |                |
| acked_at     | timestamp(3) | YES  |     | NULL                 |                |
| completed_at | timestamp(3) | YES  |     | NULL                 |                |
+--------------+--------------+------+-----+----------------------+----------------+

MariaDB [wildlink_db]> SHOW COLUMNS FROM node_status_current;
+------------+-------------+------+-----+---------------------+-------------------------------+
| Field      | Type        | Null | Key | Default             | Extra                         |
+------------+-------------+------+-----+---------------------+-------------------------------+
| sys_id     | varchar(50) | NO   | PRI | NULL                |                               |
| vst_type   | varchar(50) | NO   | PRI | NULL                |                               |
| val_status | varchar(20) | YES  |     | idle                |                               |
| val_params | longtext    | YES  |     | NULL                |                               |
| updated_at | datetime    | YES  |     | current_timestamp() | on update current_timestamp() |
+------------+-------------+------+-----+---------------------+-------------------------------+

MariaDB [wildlink_db]> SHOW COLUMNS FROM vst_links;
+--------------+-------------+------+-----+---------------------+----------------+
| Field        | Type        | Null | Key | Default             | Extra          |
+--------------+-------------+------+-----+---------------------+----------------+
| id           | int(11)     | NO   | PRI | NULL                | auto_increment |
| sys_id       | varchar(50) | NO   |     | NULL                |                |
| source_role  | varchar(50) | NO   |     | NULL                |                |
| target_role  | varchar(50) | NO   |     | NULL                |                |
| event_type   | varchar(50) | YES  |     | any                 |                |
| val_interval | int(11)     | YES  |     | 30                  |                |
| val_enabled  | tinyint(1)  | YES  |     | 1                   |                |
| created_at   | timestamp   | YES  |     | current_timestamp() |                |
+--------------+-------------+------+-----+---------------------+----------------+

MariaDB [wildlink_db]> SHOW COLUMNS FROM node_data;
+------------+-------------+------+-----+---------------------+----------------+
| Field      | Type        | Null | Key | Default             | Extra          |
+------------+-------------+------+-----+---------------------+----------------+
| id         | int(11)     | NO   | PRI | NULL                | auto_increment |
| sys_id     | varchar(50) | NO   |     | NULL                |                |
| env_temp   | float       | YES  |     | NULL                |                |
| env_hum    | float       | YES  |     | NULL                |                |
| env_pres   | float       | YES  |     | NULL                |                |
| env_lux    | float       | YES  |     | NULL                |                |
| log_msg    | text        | YES  |     | NULL                |                |
| raw_data   | longtext    | YES  |     | NULL                |                |
| created_at | timestamp   | YES  |     | current_timestamp() |                |
+------------+-------------+------+-----+---------------------+----------------+

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
| created_at  | timestamp   | YES  |     | current_timestamp() |                |
| log_ext     | longtext    | YES  |     | NULL                |                |
+-------------+-------------+------+-----+---------------------+----------------+
