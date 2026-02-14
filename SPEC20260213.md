# WildLink 命名規約仕様書 (SPEC.md)
更新日: 2026-02-12

## 1. 項目名接頭語 (Prefix)
すべての項目名は以下の接頭語を使用し、すべて小文字で表記する。

| 接頭語 | 意味 | 項目例 |
| :--- | :--- | :--- |
| **hw_** | 物理固定/ハードウェア | hw_pin, hw_driver, hw_bus, hw_addr |
| **val_** | 動作設定/変数 | val_interval, val_enabled, val_res, val_name |
| **act_** | 発動条件/制御 | act_line, act_rec, act_strobe, act_stream |
| **env_** | 測定数値 (環境) | env_temp, env_hum, env_pres, env_lux |
| **sys_** | 本体状態 (システム) | sys_cpu_t, sys_volt, sys_disk, sys_up, sys_id |
| **log_** | 記録/履歴 | log_level, log_msg, log_code, log_ext |
| **net_** | 通信関連 | net_ssid, net_rssi, net_ip |
| **loc_** | 位置情報 | loc_lat, loc_lon, loc_dir |

## 2. 基本データ型 (Data Types)
- **Boolean**: `true` / `false`
- **DateTime**: ISO 8601 形式 (`YYYY-MM-DDTHH:MM:SS`)
- **Status**: 
    - `val_status`: 物理的な接続・動作状態
    - `val_paused`: 一時停止フラグ (true/false)

## 3. MQTT トピック構造
- **Command**: `wildlink/{sys_id}/cmd` (Payload: `cam_start`, `cam_stop` 等の文字列)
- **Data**: `wildlink/{sys_id}/data` (Payload: JSON形式のセンサーデータ)

## 4. 標準ディレクトリ構造 (Deployment Standard)
システムの一貫性を保つため、全ノードで以下の構造を維持する。

| パス | 役割 | 主な内容 |
| :--- | :--- | :--- |
| `/opt/wildlink/common/` | 共通ライブラリ | `wmp_core.py`, 通信プロトコル定義 |
| `/opt/wildlink/config/` | 設定・認証 | `node_config.json`, `.env` |
| `/opt/wildlink/hub/` | サーバー機能 (Pi 2) | `wmp_stream_rx.py`, API, DB連携 |
| `/opt/wildlink/node/` | 端末機能 (Pi Zero) | `main_manager.py` |
| `/opt/wildlink/node/units/` | 物理制御 | 各種センサー/カメラ送信ユニット (`tx`) |

### パス参照の標準（Python）
ユニットから `common` を参照する際は、必ず自身の場所から2段遡る実装とする。

## 5. データベース設計 (VSTプラグイン対応版)

### テーブル構成
1. **nodes (戸籍)**: ノードの属性・位置・電源情報。
2. **node_configs (動作設定)**: VST（プラグイン）のパラメータ、動作間隔、解像度等。
3. **sensor_logs (履歴)**: 測定数値、システム状態。
4. **command_logs (指令)**: 実行されたアクションの履歴。


-- WildLink Database Standard Schema (2026-02-12)
-- 既存テーブルの削除（順番に注意）
DROP TABLE IF EXISTS node_configs;
DROP TABLE IF EXISTS command_logs;
DROP TABLE IF EXISTS sensor_logs;
DROP TABLE IF EXISTS nodes;

-- 1. nodes (戸籍テーブル)
CREATE TABLE nodes (
    sys_id VARCHAR(50) PRIMARY KEY,
    val_name VARCHAR(100),       -- ノードの愛称
    loc_name VARCHAR(100),       -- 設置場所 (例: 裏山第一)
    loc_lat DECIMAL(10, 7),      -- 緯度
    loc_lon DECIMAL(10, 7),      -- 経度
    hw_pwr_src VARCHAR(20),      -- 電源 (battery/solar/ac)
    net_ip VARCHAR(15),          -- 最終確認IP
    sys_status VARCHAR(20),      -- online/offline/maintenance
    val_ui_layout JSON,          -- VSTカードの並び順
    log_note TEXT,               -- 自由記述メモ
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 2. node_configs (VST設定・動作パラメータ)
CREATE TABLE node_configs (
    sys_id VARCHAR(50),
    dev_type VARCHAR(50),        -- camera, dht22, etc.
    val_params JSON,             -- {"val_res": "640x480", "ui_type": "camera"}
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (sys_id, dev_type),
    FOREIGN KEY (sys_id) REFERENCES nodes(sys_id) ON DELETE CASCADE
);

-- 3. sensor_logs (データ履歴)
CREATE TABLE sensor_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sys_id VARCHAR(50),
    env_temp FLOAT,
    env_hum FLOAT,
    sys_volt FLOAT,
    raw_data JSON,               -- 受信した全生データ
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX (sys_id),
    INDEX (created_at)
);

-- 4. command_logs (指令履歴)
CREATE TABLE command_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sys_id VARCHAR(50),
    act_type VARCHAR(50),         -- cam_start, cam_stop 等
    status VARCHAR(20),           -- sent/success/failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX (sys_id)
);

-------------------------------------------------------------
WildLink System Spec (2026-02-11 Update)
    Naming: act_stream (映像配信フラグ), val_status (動作状態)
    DB Table: nodes, command_logs, sensor_logs (JSON raw_data 含む)
    Directory:
        /opt/wildlink/common/ (wmp_core.py)
        /opt/wildlink/node/units/ (unit_camera_v1.py, wmp_stream_tx.py)
    Path Rule: Pythonスクリプトは自身の場所から2段遡って common を path に追加する。

## 6. インターフェース定義 (WildLink VST Interface Standard v1.0) (2026-02-12)
マネージャーが各ユニット（WildLink VST (Virtual Sensor Technology)）をどう扱い、Web UIがどう表示するかの規約である

1. ユニット・クラス構成 (Unit Class)
すべてのユニットは、以下のメソッドを実装しなければならない。
    メソッド名      引数    戻り値      役割
__init__(config)    dict	なし	config（DBのval_params）を受け取り初期化
update(commands)	dict	dict	MQTT等の指示を受け取り、現在の状態（val_status等）を返す

2. 通信・データ交換規約
・Input (Command): マネージャーからユニットへ渡す辞書型。
    例: {"act_stream": true, "val_interval": 10}
・Output (Status/Log): ユニットからマネージャーへ返す辞書型。
    例: {"val_status": "streaming", "env_temp": 25.5, "log_msg": "OK"}

3. データベース連動 (VST Meta Data)
Web UIが「どんなカードを作るべきか」を判断するための node_configs.val_params 内の標準キーです。
・ui_type: camera, sensor_card, toggle_switch, gauge
・ui_order: 表示順序 (int)
・ui_color: テーマカラー (CSS color)

### VST (Virtual Sensor Technology) インターフェース規約 (2026-02-13)

全てのノード側デバイスユニットは、`common/vst_base.py` の `WildLinkVSTBase` を継承すること。

1. **基本メソッド**
   - `__init__(self, config)`: DBの `val_params` (JSON) を受け取り、属性(self.val_xxx)を初期化する。
   - `update(self, act_cmds)`: 毎秒実行される。`act_cmds`（MQTT経由の指示）を受け取り、最新の状態を辞書で返す。
   - `sense(self)`: `val_interval` 周期で実行される。センサー値の取得ロジックをここに記述する。
   - `execute_actions(self, cmds)`: `act_xxx` 系の命令が届いた際の処理を記述する。

2. **命名規則の強制**
   - ユニット内の変数は、共通仕様書の接頭語（`env_`, `val_`, `act_`, `sys_`, `log_`）を厳守する。
   - `_report()` メソッドにより、これらの接頭語を持つ変数は自動的にMQTTでHubへ報告される。