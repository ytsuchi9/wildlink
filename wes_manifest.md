# 📄 wes_manifest.md (WES 2026 正典)

このファイルは **WildLink Event Standard (WES) 2026** の正典（Single Source of Truth）です。コード変更の際は、必ず本マニフェストの設計規格に準拠してください。

## 1. 共通設計ルール (The Core Rules)

* **トピック構造:** `nodes/{sys_id}/{vst_role_name}/{type}`
  * `type`: `cmd` (命令), `res` (応答), `event` (状態/計測)
* **動的デバイス命名 (Role-based Naming):** * ハードウェアの接続インターフェース名（例: `pi`, `usb`）はシステム管理に依存させず、役割名である `vst_role_name` (`cam_main`, `cam_sub`, `cam_rear` など) を使用して抽象化と動的切り替えを実現する。
* **命名規則の規格化:**
  * DB (`vst_class`): `Camera`, `System`, `Sensor`, `Switch` （先頭大文字）
  * ファイル名 (`vst_module`): `vst_camera.py`, `vst_system.py` （すべて小文字、接頭辞 `vst_`）
  * Pythonクラス名: `VST_Camera`, `VST_System` （`VST_` + DBの `vst_class`）

---

## 2. 変数・パラメータ命名規則 (Naming Conventions)

システム全体で変数の意味を即座に判別できるよう、以下の接頭語（すべて小文字）を厳格に適用する。基本データ型は Boolean (`true` / `false`) および DateTime (ISO 8601) を使用する。

| 接頭語 | 意味・用途 | 項目例 |
| :--- | :--- | :--- |
| `hw_` | 物理的な固定情報や設定 | `hw_pin`, `hw_driver`, `hw_bus` |
| `val_` | 動作設定・現在の状態 | `val_interval`, `val_enabled`, `val_status`, `val_res` |
| `act_` | 発動条件・トリガー | `act_run`, `act_line`, `act_rec`, `act_strobe` |
| `env_` | センサー測定数値 | `env_temp`, `env_hum`, `env_pres`, `env_lux` |
| `sys_` | 本体（Node/OS）の状態 | `sys_cpu_t`, `sys_volt`, `sys_disk`, `sys_up` |
| `log_` | 記録・履歴関連 | `log_level`, `log_msg`, `log_code`, `log_ext` |
| `net_` | 通信・ネットワーク関連 | `net_ssid`, `net_rssi`, `net_ip`, `net_port` |
| `loc_` | 位置情報 | `loc_lat`, `loc_lon`, `loc_dir` |

---

## 3. コンポーネント別責務 (Component Roles)

### [UI/API] `api/send_cmd.php`
* **役割:** ユーザー操作をDBに記録し、MQTTでNodeへ初動命令を飛ばす。
* **処理:** `INSERT INTO node_commands` (`val_status='sent'`, `sent_at=NOW()`)
* **送信:** `nodes/{sys_id}/{vst_role_name}/cmd` 宛に JSON (`{"cmd_id": ID, "act_run": true}`) をパブリッシュ。

### [HUB] Hub デーモン
Hub側は機能ごとにデーモンを分割し、明確に役割を分担する。
* **`hub_manager.py`:** コマンドのライフサイクル管理（DB監視、再送、`node_commands` の `acked_at`, `completed_at` 更新）。
* **`status_engine.py`:** Nodeからの定時報告や環境データ (`env_`)、システムログの収集専任。

### [NODE] `node/main_manager.py`
* **役割:** 自身の `sys_id` 宛の命令を受信し、適切な `VstUnit` へ分配する。
* **処理:** `nodes/{my_id}/+/cmd` を一括購読。受領直後に `acknowledged` を返送し、対象ユニットの `control(payload)` を呼び出す。

### [DRV] `node/vst_*.py` (例: vst_camera.py)
* **役割:** 物理デバイスの制御、および実行状態の報告。基底クラスの `send_response(status)` を必ず実装・利用する。
* **処理:** `control(payload)` を入口とし、完了時または状態変化時に `completed`, `error`, `idle` などを送信する。

---

## 4. コマンド応答プロトコル (Response Architecture)

WES 2026 では、トランザクション管理（プロトコル層）とデバイス動作状態（デバイス層）を独立して管理する。すべての応答 (`/res` トピック) は `cmd_status`, `val_status`, `ref_cmd_id` を含む。

### 応答ステータス定義
1. **`cmd_status` (プロトコル層 - DBトランザクション用)**
   * `acknowledged`: Nodeが命令を受信。Hubは `acked_at` を更新。
   * `completed`: 命令が正常終了。Hubは `completed_at` を更新し、命令をクローズ。
   * `failed`: 異常終了・配送失敗。
2. **`val_status` (デバイス状態層 - UI表示用)**
   * `idle`, `streaming`, `starting`, `error`, `maintenance` など、現在の物理・論理状態。

### ライフサイクルフロー
1. **Sent:** Hubが `sent` としてDBに記録・送信。
2. **ACK:** Nodeの `MainManager` が受信後、即座に `cmd_status: acknowledged` を返信。
3. **Execute:** VSTユニットが処理を実行。
4. **Completed:** 実行完了時、VSTユニットが `cmd_status: completed` と最新の `val_status` を返信。

---

## 5. 高度なシステム設計コンセプト

### A. DB操作とパッチ適用 (CRUD & Boot-time Patching)
* `cmd_json` は単なる命令ではなく、DBに「変更内容のパッチ（差分）」として格納する CRUD 概念を採用。
* PiZero等の末端デバイスは、起動時にローカルのJSON設定とHub側の設定を比較し、齟齬があれば「差分パッチ」を即座に読み込んで適用・リロードする自律ロジックを持つ。

### B. エラーコードとロギング (Hybrid Error Codes)
* HTTPステータスコードと Linux/POSIX エラー番号を組み合わせたハイブリッド方式を採用。
  * `100`番台 (進行中), `200`番台 (成功), `400`番台 (要求エラー), `500`番台 (ハード・システムエラー)。
* エラーコードとログを連携させ、履歴重視の信頼性の高いシステムを構築する（詳細は `error_codes_reference.md` にて管理）。

### C. 自律稼働モード (Autonomous / Survival Mode)
* **トリガー:** MQTT切断検知、通信タイムアウト、または `sys_volt` の異常低下。
* **振る舞い:** * センサー計測・動体検知を継続し、ログをローカルにバッチ蓄積。
  * 強い衝撃（加速度センサー `act_strobe` 等）を検知した場合は、LINEユニット等への即時アラートと証拠写真ストリーミングを試行。
  * 通信・電源回復時に、蓄積したデータをHubへ一括同期。

### D. ハードウェア寿命の保護 (Hardware Longevity)
* **ストレージ保護:** ストリーミング用一時ファイルや高頻度更新ファイルは必ず RAMディスク (`/dev/shm`) に配置し、SDカードの摩耗を防ぐ。
* **省電力制御:** バッテリー駆動デバイスは、電源状況に応じてポーリング間隔や `val_res` (解像度) を動的に下げ、消費電力を抑制する。

---

## 6. 環境変数とシステム設定

システム全体の設定優先順位は **(1) 環境変数 > (2) .envファイル > (3) DB `node_configs`** とする。

| 変数名 | 意味・役割 | 規定値・例 | 備考 |
| :--- | :--- | :--- | :--- |
| `WES_SYS_ID` | システム個体識別ID | `node_001`, `hub_001` | 未設定時はMACアドレス下6桁から自動生成 |
| `WES_MODE` | 動作モード | `node` or `hub` | `config_loader` が自動判定 |
| `WES_DB_HOST` | 接続先DBホスト | `localhost` or `192.168.x.x` | |
| `WES_LOG_LEVEL`| ログ出力レベル | `debug`, `info`, `warn`, `error`| |

### `common/config_loader.py` 規格
* 起動時に一度だけ読み込まれる **Singleton（単一保持）** 構造。
* **役割:** SYS_IDの確定、DB接続情報の保持、環境変数のパッチ適用。
* **メソッド:** `get_config(key)` で値を返し、存在しない場合は例外を投げるか安全な規定値を返す。

---

## 7. 当面の修正・移行要件 (Immediate Action Items)

コードベースを本規格に完全に適合させるための確認事項：
1. **`vst_camera.py`**: コマンド受付メソッドは旧 `execute_logic` ではなく `control(payload)` に統一する。
2. **`vst_camera.py`**: `start_streaming()` 成功時および `stop_streaming()` 完了時に、Hub側で `completed_at` が更新されるよう `cmd_status: completed` を送信する。
3. **`hub_manager.py`**: DB更新時、`vst_type` ではなく `vst_role_name` カラムをキーとして処理を行う。


### 14. Node起動時のステータスリセット (Boot-time Status Reset)
Nodeが不慮の電源断やクラッシュで停止した場合、DB上に「配信中(streaming)」などの古い状態（ゾンビステータス）が残るのを防ぐためのルール。
* **処理:** `MainManager.py` は起動直後の初期化フェーズで、必ず自身の `sys_id` に紐づく全 VST ユニットのDBステータスをリセット（`idle` や `offline` 等へ初期化）しなければならない。

### 15. 外部プロセスの厳格なライフサイクル管理 (Subprocess Lifecycle Management)
`ffmpeg` や `rpicam-vid` など、ハードウェアリソース（カメラ等）を占有する外部プロセスを起動する VST ユニットに対する厳格な終了ルール。
* **処理:** `stop()` または `stop_streaming()` メソッド内において、必ず以下の手順を踏むこと。
  1. `.terminate()` で終了シグナルを送る。
  2. `.wait(timeout)` で正常終了を待機する。
  3. タイムアウトした場合は `.kill()` で強制終了させ、プロセスを確実に解放する。
* **目的:** プロセスのゾンビ化によるハードウェアのロック状態（次回起動時にデバイスビジーで失敗する現象）を完全に防ぐ。

### 16. モジュールの動的リロード (Hot Reloading)
開発効率の向上およびダウンタイム最小化のためのルール。
* **処理:** Nodeの `MainManager` は、Hubから設定変更（または `action: reload`）を受信した際、システム全体を再起動するのではなく、Pythonの `importlib.reload()` を用いて対象の VST ユニットモジュールのみを動的に再読み込みし、インスタンスを再生成する。