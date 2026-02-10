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