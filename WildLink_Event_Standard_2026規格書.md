## WildLink Event Standard (WES) 2026 規格書

### 1. 概要
本規格は、IoTノード（Raspberry Pi等）、サーバー（PHP/DB）、およびクライアント（Webブラウザ）間における、MQTTを用いた双方向通信のトピック構造およびデータ形式を定義する。

### 2. 命名規則（接頭語）
全てのデータ項目は、その性質を示す接頭語を付与する。
* `hw_`: 物理固定設定（例: `hw_pin`, `hw_bus`）
* `val_`: 動的設定・状態（例: `val_status`, `val_enabled`）
* `act_`: 発動条件・アクション（例: `act_run`, `act_line`）
* `env_`: 環境測定数値（例: `env_temp`, `env_hum`）
* `sys_`: システム本体状態（例: `sys_cpu_t`, `sys_volt`）
* `net_`: 通信関連（例: `net_rssi`, `net_ip`）

### 3. MQTTトピック構造（Role-Based Hierarchy）
無駄な通信を抑制し、特定の「役割（Role）」に絞った購読を可能にするため、以下の階層を採用する。

| 種類 | トピック形式 | 方向 | 説明 |
| :--- | :--- | :--- | :--- |
| **Command** | `nodes/{node_id}/{role}/cmd` | S → N | デバイスへの操作命令 |
| **Event** | `nodes/{node_id}/{role}/event` | N → S/C | 状態変化、命令への応答、トリガー通知 |
| **Environment**| `nodes/{node_id}/{role}/env` | N → S | センサー生データ（定時報告用） |
| **System** | `nodes/{node_id}/sys` | N → S | ノード全体のバイタル情報（CPU等） |

### 4. ペイロード構造（JSON）

#### 4.1. Command (命令)
```json
{
  "action": "start",
  "act_run": true,
  "cmd_id": 123
}
```

#### 4.2. Event (状態変化・応答)
```json
{
  "role": "cam_main",
  "event": "stream_ready",
  "val_status": "streaming",
  "ref_cmd_id": 123
}
```
* `ref_cmd_id`: Commandに対する応答の場合、その `cmd_id` を含める。

#### 4.3. Environment (環境データ)
```json
{
  "env_temp": 24.5,
  "env_hum": 60.2,
  "val_time": "2026-03-26T23:45:00Z"
}
```