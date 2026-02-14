WildLink システム詳細仕様書 (SPEC.md)
1. 物理配置・動作環境
Hub (Parent): Raspberry Pi 2 (IP: 192.168.0.102)

Node (Child): Raspberry Pi Zero (IP: 192.168.0.xxx)

共通ルートパス: /opt/wildlink (シンボリックリンク推奨)

通信: MQTT (Port 1883), UDP (Port 5005), HTTP (Port 8080)

2. 環境変数管理 (.env)
セキュリティとポータビリティのため、以下のキーを /opt/wildlink/.env に定義する。

MQTT_BROKER: MQTTブローカー（Hub）のIPアドレス

DB_HOST: DBサーバー（Hub）のIPアドレス (Hub自身は 127.0.0.1)

DB_USER: データベース接続ユーザー名

DB_PASS: データベース接続パスワード

DB_NAME: 使用データベース名 (wildlink_db)

NODE_ID: ノード識別子 (例: node_001)

3. 命名規則・データ型
接頭語ルール
hw_: 物理固定 (例: hw_pin, hw_bus, hw_driver)

val_: 動作設定 (例: val_enabled, val_interval, val_res, val_fps)

act_: 発動条件・指令 (例: act_stream, act_line, act_config_reload)

env_: 測定数値 (例: env_temp, env_hum, env_volt, env_lux)

sys_: 本体状態 (例: sys_cpu_t, sys_volt, sys_up, sys_disk)

net_: 通信関連 (例: net_ssid, net_rssi, net_ip)

log_: 記録/履歴 (例: log_level, log_msg, log_code)

基本型
Boolean: true / false

DateTime: ISO 8601 形式

Status: val_status (稼働状態), val_paused (一時停止)

4. データベース定義 (Schema v1.1)
構成管理テーブル
nodes: ノードの静的情報 (sys_id, val_name, loc_lat, loc_lon)

device_catalog: VSTユニットの索引 (vst_type, vst_class, vst_module, default_params)

node_configs: ノードごとの動的構成 (sys_id, vst_type, val_params, val_enabled)

ログ蓄積テーブル
sensor_logs: 環境測定値 (env_系) を格納。JSON形式の raw_data を併設。

system_logs: 本体の健康状態 (sys_系, net_系) を格納。

5. ソフトウェアコンポーネント詳細
A. main_manager.py (Node側)
役割: 起動時にHubのDBから自ノードの node_configs を取得し、対応するVSTクラスを動的に importlib でロード・インスタンス化する。

メインループ: 1秒周期で全VSTの update(current_commands) を実行し、戻り値を一括してMQTT (wildlink/{node_id}/res) へパブリッシュする。

B. hub_manager.py (Hub側)
役割: MQTT (wildlink/+/res) を常時監視。

仕分けロジック: 受信したJSONのキーを走査し、env_ で始まる場合は sensor_logs へ、sys_ または net_ で始まる場合は system_logs へ自動的に INSERT する。

C. wmp_stream_rx.py (Hub側)
役割: Nodeから送出されるUDPパケットを wmp_core を用いて再構築。

配信: MJPEG形式でHTTP配信 (/stream)。マルチスレッドにより、複数の閲覧者やDB保存処理と干渉せずに映像を維持する。

6. 既知の課題と今後の拡張
終了時ラグ: FFmpegプロセスのクリーンアップとMQTTのDisconnect処理に時間がかかる。シグナルハンドリングの改善が必要。

ローカルキャッシュ: DB切断時の起動を保証するため、起動時に取得したDB情報を /opt/wildlink/node/config_cache.json に保存・参照する仕組みを導入予定。

再読み込み機能: act_config_reload: true を受け取った際、マネージャーを再起動せずにVSTユニットの再生成を行う処理の追加。