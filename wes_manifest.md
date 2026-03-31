## 📄 wes_manifest.md (Provisional v1.0)

このファイルは **WildLink Event Standard (WES) 2026** の正典（Single Source of Truth）です。コード変更の前に必ずここを更新してください。

### 0. 共通設計ルール (The Core Rules)
* **トピック構造:** `nodes/{sys_id}/{vst_role_name}/{type}`
    * `type`: `cmd` (命令), `res` (応答), `event` (状態/計測)
* **コマンドライフサイクル:** 1. `sent`: UI/Hubが発行 
    2. `acknowledged`: Nodeが受領 
    3. `completed`: Nodeが実行完了（配信開始など）
* **変数命名規則:** `hw_` (ハード), `val_` (設定/状態), `act_` (制御), `log_` (履歴)
* **基底クラスの必須メソッド:** send_response(status)
    * 役割: 全ての VST ユニットは、このメソッドを通じて Hub へ completed や idle を報告しなければならない。
* **Hub 応答処理ルール:**
    1. Hubは res トピックから val_status を読み取る。
    2. val_status == 'acknowledged' なら acked_at を更新。
    3. val_status == 'completed' なら completed_at を更新。
    4. それ以外（idle, streaming, error）は node_status_current の更新のみ行う。
* **命名規則の規格化:**
    * DB (vst_class): Camera, System, Sensor, Switch （先頭大文字）
    * ファイル名 (vst_module): vst_camera.py, vst_system.py, vst_sensor.py （すべて小文字、接頭辞 vst_）
    * Pythonクラス名: VST_Camera, VST_System, VST_Sensor （VST_ + DBの vst_class）
        MainManager 内の以下のロジックはこの規格に則っている
            full_class_name = class_name if class_name.startswith("VST_") else f"VST_{class_name}"

---

### 1. [UI/API] `api/send_cmd.php`
**役割:** ユーザー操作をDBに記録し、MQTTでNodeへ初動命令を飛ばす。

| 項目 | 定義 / パラメータ | 備考 |
| :--- | :--- | :--- |
| **Main Action** | `POST` リクエスト処理 | UIボタンからの発火 |
| **DB Write** | `INSERT INTO node_commands` | `val_status='sent'`, `sent_at=NOW()` |
| **MQTT Pub** | `nodes/{sys_id}/{vst_role_name}/cmd` | JSON: `{"cmd_id": ID, "act_run": true, ...}` |

---

### 2. [HUB] `hub/hub_manager.py`
**役割:** DBの監視、Nodeへの命令転送、およびNodeからのレスポンスによるDB更新。

| 項目 | メソッド / 定義 | 役割 |
| :--- | :--- | :--- |
| **DB Monitor** | `_db_monitor_loop()` | `sent` 状態の未送信コマンドを検索し再送 |
| **MQTT Sub** | `nodes/+/+/res` | Nodeからの `acknowledged` / `completed` 受信 |
| **MQTT Sub** | `nodes/+/+/event` | Nodeからの定期状態報告・エラー報告受信 |
| **DB Update** | `update_command_status()` | 受信データに基づき `node_commands` を更新 |

---

### 3. [NODE] `node/main_manager.py`
**役割:** 自分の `sys_id` 宛の命令を受信し、適切な `VstUnit` (役割) へ分配する。

| 項目 | メソッド / 定義 | 役割 |
| :--- | :--- | :--- |
| **MQTT Sub** | `nodes/{my_id}/+/cmd` | 自身への命令を全取得（ワイルドカード使用） |
| **Dispatcher** | `dispatch_command(role, payload)` | 命令を `VstUnit[role].control(payload)` へ渡す |
| **Response** | `send_ack(cmd_id)` | 受領後即座に `res` トピックへ `acknowledged` を返送 |

---

### 4. [DRV] `node/vst_camera.py`
**役割:** カメラデバイスの制御、および配信状態の管理・報告。

| 項目 | メソッド / 定義 | 役割 |
| :--- | :--- | :--- |
| **Interface** | **`control(payload)`** | **命令の入口 (固定)** ※旧 `execute_logic` から変更 |
| **Action** | `start_streaming()` | プロセス起動・`completed` 通知のトリガー |
| **Action** | `stop_streaming()` | プロセス停止・`idle` 状態への遷移 |
| **Response** | `send_response(status)` | `streaming`, `idle`, `error` などの状態を `res` へ送信 |
| **Streaming** | `_streaming_loop()` | スレッド内での実際の映像キャプチャ・WMP送信 |

---

### 修正が必要な「ブレ」のポイント（即時対応用）
1.  **`vst_camera.py`**: `execute_logic` を `control` にリネームする。
2.  **`vst_camera.py`**: `start_streaming()` の成功後に、Hubが `completed_at` を書けるように `completed` ステータスを送信するロジックを追加する。
3.  **`hub_manager.py`**: `res` トピックをパースする際、`vst_type` ではなく `vst_role_name` カラムを更新するように確認する。

---

## 6. コマンド応答プロトコル (Response Architecture)

WES 2026 では、コマンドの実行結果とデバイスの状態を独立して管理する。

### 6.1 応答ペイロード構造
すべての応答 (`/res` トピック) は以下のキーを含まなければならない。

- `cmd_status` (string): 命令のライフサイクル状態。
  - `acknowledged`: 受領完了（NodeのManagerが送信）。
  - `completed`: 正常終了（VSTユニットが送信）。
  - `failed`: 異常終了（VSTユニットが送信）。
- `val_status` (string): デバイスの現在の物理動作状態。
  - `idle`, `streaming`, `starting`, `error`, `maintenance` など。
- `ref_cmd_id` (int): 関連するコマンドID。

### 6.2 処理フロー
1. **Hub -> Node**: コマンド送信。
2. **MainManager**: `cmd_status: acknowledged` を返信し、DBの `acked_at` を更新。
3. **VST Unit**: 処理開始。完了または失敗時に `cmd_status: completed/failed` と最新の `val_status` を返信。
4. **HubManager**: `cmd_status` を見て `completed_at` を更新し、同時に `val_status` を見て `node_status_current` を更新する。