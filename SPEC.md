# WildLink 命名規約仕様書 (SPEC.md)
更新日: 2026-02-11

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

## 5. データベース構造
-- WildLink Database Standard Schema (2026-02-11)

-- 1. ノードマスタ (sys_id が主キー)
CREATE TABLE nodes (
    sys_id VARCHAR(50) PRIMARY KEY, -- 例: 'node_001'
    val_name VARCHAR(100),          -- 表示名
    net_ip VARCHAR(15),             -- 最終IP
    sys_status VARCHAR(20),         -- online/offline
    val_ui_config JSON,             -- UIの並び順等の設定
    last_update DATETIME
);

-- 2. コマンド履歴 (act_type 接頭語を使用)
CREATE TABLE command_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sys_id VARCHAR(50),
    act_type VARCHAR(50),           -- 'cam_start', 'cam_stop' 等
    status VARCHAR(20),             -- 'sent', 'success', 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. 環境・システムデータ (env_, sys_ 接頭語を使用)
CREATE TABLE sensor_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sys_id VARCHAR(50),
    env_temp FLOAT,
    env_hum FLOAT,
    env_pres FLOAT,
    sys_volt FLOAT,
    sys_cpu_t FLOAT,
    log_msg TEXT,
    raw_data JSON,                  -- 受信した全JSONデータをそのまま保存
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-------------------------------------------------------------
WildLink System Spec (2026-02-11 Update)
    Naming: act_stream (映像配信フラグ), val_status (動作状態)
    DB Table: nodes, command_logs, sensor_logs (JSON raw_data 含む)
    Directory:
        /opt/wildlink/common/ (wmp_core.py)
        /opt/wildlink/node/units/ (unit_camera_v1.py, wmp_stream_tx.py)
    Path Rule: Pythonスクリプトは自身の場所から2段遡って common を path に追加する。