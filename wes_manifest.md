# 📄 wes_manifest.md (WES 2026 正典)

このファイルは **WildLink Event Standard (WES) 2026** の正典（Single Source of Truth）です。コード変更の際は、必ず本マニフェストの設計規格に準拠してください。

## 1. 共通設計ルール (The Core Rules)

              * **トピック構造:** `wildlink/{sys_id}/{vst_role_name}/{type}`
                * `type`: `cmd` (命令), `res` (応答), `event` (状態/計測)
              * **動的デバイス命名 (Role-based Naming):** * ハードウェアの接続インターフェース名（例: `pi`, `usb`）はシステム管理に依存させず、役割名である `vst_role_name` (`cam_main`, `cam_sub`, `cam_rear` など) を使用して抽象化と動的切り替えを実現する。
              * **命名規則の規格化:**
                * DB (`vst_class`): `Camera`, `System`, `Sensor`, `Switch` （先頭大文字）
                * ファイル名 (`vst_module`): `vst_camera.py`, `vst_system.py` （すべて小文字、接頭辞 `vst_`）
                * Pythonクラス名: `VST_Camera`, `VST_System` （`VST_` + DBの `vst_class`）

# グループ概念と完全疎結合 (.env定義):

* 各ノード/ハブは .env に SYS_GROUP (例: kyoto_hq, hokkaido_branch) を定義し、自身が所属する論理グループを認識する。

* 物理的なネットワークやDB/Hubの固定IP (HUB_IP 等) には依存せず、設定された MQTT_BROKER に繋がりさえすれば、同じグループのインフラに合流できる「プラグ＆プレイ」な設計とする。

# トピック構造とルーティング:

* アプリ層（不変）: wildlink/{sys_id}/{vst_role_name}/{type} (type: cmd, res, event)

* インフラ層（拡張）: エッジとクラウド等ネットワークが分かれる場合、コード上のトピック階層は変更せず、mosquitto.conf のブリッジ機能 (topic wildlink/# both 1 "" {SYS_GROUP}/ 等) を用いて、ブローカー間で自律的に配信範囲を制御する。

# 動的デバイス命名 (Role-based Naming):
* ハードウェアの接続インターフェース名（例: pi, usb）はシステム管理に依存させず、役割名である vst_role_name (cam_main, cam_sub, cam_rear など) を使用して抽象化と動的切り替えを実現する。

# 命名規則の規格化:

* DB (vst_class): Camera, System, Sensor, Switch （先頭大文字）
* ファイル名 (vst_module): vst_camera.py, vst_system.py （すべて小文字、接頭辞 vst_）
* Pythonクラス名: VST_Camera, VST_System （VST_ + DBの vst_class）

# 共通ライブラリの徹底:
* プロトコルやアーキテクチャの変更（フェーズ移行）を吸収するため、各モジュールからの通信・データ処理は必ず common/mqtt_client.py, common/db_bridge.py などのインターフェースを経由させる。

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

2. 環境変数設定規格 (.env Standards)
システム全体で統一された .env キーを使用し、環境依存のハードコードを排除する。
# 基本情報
* SYS_GROUP: 所属する論理エリア/グループ名（ルーティングおよびブリッジ制御用）
* SYS_ID: ノード自身の個体識別ID (Nodeのみ必須)
# 通信関連 (MQTT)
* MQTT_BROKER: 接続先ブローカーのIPアドレスまたはドメイン
* MQTT_PORT: 接続ポート (デフォルト: 1883)
# データベース関連
* DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME
* ※セキュリティ指針: フェーズ3移行後は、Node側の .env からDB接続情報を完全に削除し、Hub/Backend側のみで管理する。




## 3. コンポーネント別責務 (Component Roles)

                  ### [UI/API] `api/send_cmd.php`
                  * **役割:** ユーザー操作をDBに記録し、MQTTでNodeへ初動命令を飛ばす。
                  * **処理:** `INSERT INTO node_commands` (`val_status='sent'`, `sent_at=NOW()`)
                  * **送信:** `wildlink/{sys_id}/{vst_role_name}/cmd` 宛に JSON (`{"cmd_id": ID, "act_run": true}`) をパブリッシュ。

                  ### [HUB] Hub デーモン
                  Hub側は機能ごとにデーモンを分割し、明確に役割を分担する。
                  * **`hub_manager.py`:** コマンドのライフサイクル管理（DB監視、再送、`node_commands` の `acked_at`, `completed_at` 更新）。
                  * **`status_engine.py`:** Nodeからの定時報告や環境データ (`env_`)、システムログの収集専任。

                  ### [NODE] `node/main_manager.py`
                  * **役割:** 自身の `sys_id` 宛の命令を受信し、適切な `VstUnit` へ分配する。
                  * **処理:** `wildlink/{my_id}/+/cmd` を一括購読。受領直後に `acknowledged` を返送し、対象ユニットの `control(payload)` を呼び出す。

                  ### [DRV] `node/vst_*.py` (例: vst_camera.py)
                  * **役割:** 物理デバイスの制御、および実行状態の報告。基底クラスの `send_response(status)` を必ず実装・利用する。
                  * **処理:** `control(payload)` を入口とし、完了時または状態変化時に `completed`, `error`, `idle` などを送信する。

## 3. コンポーネント別責務 (Component Roles) 段階的移行モデル
将来の大規模化・分散化・高セキュリティ化に備え、アーキテクチャを段階的に引き上げる。

# * ** 【フェーズ2】イベント駆動の導入（Hubによるコマンド一元管理）
UIからの直接命令による競合（二重送信）を防ぎ、Hubを指揮者とする構成。

# [UI/API] api/send_cmd.php

* 役割: ユーザー操作をDBに記録し、関連モジュールに「更新の合図」のみを通知する。
* 処理: INSERT INTO node_commands (val_status='pending', sent_at=NOW())
* 送信: コマンド本体は送らず、system/hub/kick 宛に空の通知をパブリッシュする。

# [HUB] hub_manager.py (Hub デーモン)

* 役割: キック通知を契機とした完全イベント駆動のコマンドディスパッチ（DB監視ループの廃止）。
* 処理: system/hub/kick を購読。受信時のみDBから pending を取得し、対象Node（wildlink/{sys_id}/{vst_role_name}/cmd）へパブリッシュ。コマンド送信時後、DBを sent に更新。

# [NODE] node/main_manager.py & vst_*.py

* 役割: 制御コマンドのライフサイクル応答と、純粋なデータ（映像・環境値）ストリームの経路を厳格に分離する（0.2KB化け等のノイズ混入の完全排除）。
* コマンドを受信した直後、実際の処理（ffmpegの起動や停止など）を開始する前に、cmd_status: "acknowledged" をHubに返すメソッドを実行する。
* 処理が正常終了した場合：従来通り cmd_status: "completed" を返す。
* 処理中にエラーを捕捉した場合：cmd_status: "failed" を返す。

# DB層 (db_bridge.py)

* 厳密に送られてきたステータス通りに acked_at と completed_at を埋める。
* エラー時も completed_at に時刻を記録する。

# * ** 【フェーズ3】完全疎結合（DBアクセスの一元化とEvent Sourcing）
* NodeからDBへの直接アクセス権を剥奪し、セキュリティと耐障害性を最大化する構成。

# [NODE] 各種ノードモジュール

* 役割 (変更): DBへの直接接続を完全廃止。すべての測定データ (env_)、状態変化、ログ、コマンド応答を wildlink/.../event や res としてMQTTへ放流（Fire and Forget）するのみとする。

# [HUB/BACKEND] db_writer.py (新規/統合)

* 役割: 全NodeからMQTTに放流される膨大なイベント・レスポンスを購読し、一括してDBへの書き込み（INSERT/UPDATE）を担当する専任デーモン。QoSを活用してデータの欠損を防ぐ。

# Hub Status Engine (status_engine.py) [今後のフェーズ]

* DBを巡回し、長時間 pending, sent, acknowledged で止まっているコマンドをtimeout (エラー扱い) としてクローズし、completed_at に時刻を刻むロジックを追加する。

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

### E. VSTユニットからDBへ報告 (update_status , execute_logic)
* 全てのVSTユニットは、任意の状態（payload）をDBへ報告する能力を持つべき
* 基底クラスの update_status は、引数なし（生存報告のみ）と、引数あり（状態データの同期）の両方を許容する「オーバーロード的振る舞い」を保証する。
* Status Interface: 基底クラスの update_status は可変引数（dict）を受け入れ、子クラスに実装を強要しない。
* Absolute Control: execute_logic は、payload のキーの有無ではなく、更新された self.属性名 の真偽値に基づいて動作を決定する。（トグル動作の禁止）
* control における setattr は execute_logic の実行前に行われることを保証する

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


WES 2026 マニフェスト：状態管理・命名規則・例外処理 統合規定
1. 状態（Status）の定義と遷移プロトコル

node_status_current テーブルの val_status は、以下の5つの「標準状態」のみを許容する。
状態名(val_status)    意味      主な更新者      解説
idle                待機中      Node (Unit)    リソースが解放され、次の命令を受け入れ可能な状態。
starting            起動処理中   Node (Unit)    命令を受理し、プロセスの立ち上げやハードウェア初期化中。
streaming           実行中/配信中 Hub (RX)      実際にデータ（動画等）が目的地に到達している状態。
stopping            停止処理中    Node (Unit)   終了命令を受け、後片付け（プロセス終了等）を実行中。
error               異常発生      Hub / Node    期待された動作が失敗、または通信が途絶した状態。

【重要：更新の「真実」ルール】
  Nodeの責任: 自身の内部リソース（プロセス、スレッド）の死活に基づき starting, stopping, idle を報告する。
  Hubの責任: ネットワーク越しに届くデータの「実在」に基づき、外部から streaming または error (Timeout) を上書きする。

2. 厳格な命名規則 (Naming Convention)
コードとDBの間で混乱を招かないよう、以下のフォーマットを強制する。
① データベース・フィールド（接頭語ルール）
  hw_ (Hardware): 物理的な固定値（例: hw_driver, hw_bus_addr）
  val_ (Value): 動作設定や現在の論理状態（例: val_status, val_res, val_fps）
  act_ (Action): 発動トリガーや動作フラグ（例: act_run, act_line）
  log_ (Log): 履歴・エラー情報（例: log_code, log_msg, log_ext）
  net_ (Network): 通信関連（例: net_port, net_ip）
② Python クラス
  ・メソッドクラス名: PascalCase (例: VstCamera, MainManager)
  メソッド名: snake_case (例: start_streaming, update_status) ※動詞から開始。
  メンバ変数: self.val_status のように、DBのフィールド名と完全に一致させる。

3. エラーハンドリング・プロトコル
エラー発生時は、単に error と書くだけでなく、**「なぜ」**を機械が判別可能にする。
  log_code: 3桁の数値。
    200: 正常完了
    4xx: 設定・権限エラー（例: 404=デバイス未検出、400=不正な設定）
    5xx: 内部実行エラー（例: 500=プロセス急死、503=通信タイムアウト）
  log_ext (JSON形式)
    :再試行回数、例外メッセージ、ターゲットIP等を格納。
    例: {"target": "192.168.1.102", "retry": 3, "os_error": "Permission denied"}

4. 応答（Response）の同期ルール
「2回押し」問題を物理的に撲滅するための規定。
  非同期命令: start_streaming は starting を報告して即座に応答（Response）を返してよい。
  同期命令: stop_streaming は、必ずスレッドの完全停止（.join()）を確認してから completed を報告し、idle を書き込む。
  UIの待機: UIは completed を受け取るまで、ボタンの再活性化を行わない。

5. 異常検知および「Idle」遷移の厳格化
① 故障検知時の「隔離と報告」
  Unit内部での検知: VSTユニットが例外をキャッチ。
  ステータスの「Error固定」: val_status = 'error' に変更。
  詳細のパッキング: log_ext にデバッグ情報を格納。
  連動の停止: MainManager は対象ユニットが error の場合、関連する links（連動動作）を自動的にスキップする。
② Exit Status（終了コード）による「Idle」の区別
  val_status が idle であっても、log_code を参照して前回の終了状態を判別する。
  val_status  log_code  意味（システムの状態）  UIでの表現（例）
  idle200正常終了による待機。緑のチェック / Idle
  idle500異常終了後の自動復旧。黄色の警告 / Recovered
  error404致命的故障（デバイス紛失）。赤色の「！」 / Missing
  error503通信途絶（Hub未到達）。グレーの「？」 / Link Down

6. 例外および終了処理に関する条項
【条項16：自己診断と隔離（Self-Diagnostics）】
  全てのVSTユニットは、setup() およびループ内で自己診断を行い、異常検知時は val_status = 'error' を維持しなければならない。
  軽微なエラーでリトライ可能な場合は、log_ext に履歴を記録し、starting 状態を維持してよい。
【条項17：終了の透明性（Exit Transparency）】
  ユニットが idle に遷移する際は、必ずその原因を log_code に明示すること。
  正常な停止命令（STOPコマンド）による遷移は 200 (OK)。
  内部エラーによる強制停止は 5xx (Internal Error)。
  設定ミスによる停止は 4xx (Client Error)。

追記提案（ケーススタディ反映用）
【条項18：通信のデッドライン（Communication Deadline）】
  ネットワーク送信を伴うVSTユニットは、送信開始後、一定時間内にHub側からの受信確定（streamingへの書き換え）が行われない場合、自ら log_code: 503 をセットし、リトライまたは error 遷移を行わなければならない。

  ### 5. ステータス管理の自動生成と統合ルール

#### 【条項19：ステータスレコードの同期（Status Auto-Sync）】
* `MainManager` は起動時、`node_configs` および `vst_links` をスキャンし、`is_active = 1` の全ての項目に対して `node_status_current` にレコードが存在することを確認しなければならない。
* レコードが存在しない場合は、初期値 `val_status = 'idle'`, `log_code = 200` で即座に `INSERT` を実行する。
* `is_active = 0` となった項目については、ゴミが残らないよう `node_status_current` から削除、または明示的な無効化を行うことが推奨される。

#### 【条項20：リンク（組み合わせ）のステータス定義】
* `vst_links` テーブルのレコードに対応するステータスは、`vst_role_name` を `lnk_[id]` (例: `lnk_1`) と命名して管理する。
* リンクのステータスは、その連動機能が「現在アクティブに動作中か」を示す。
    * `idle`: トリガー待機中。
    * `streaming`: 連動によるアクション（録画、通知等）が実行中。
    * `error`: 連動プロセス内で例外が発生した。

#### 【条項21：ハードウェア異常の即時報告】
* 全てのユニットは、`setup()` 時に物理デバイス（カメラ、センサー等）の到達性を確認しなければならない。
* デバイスの認識に失敗した場合、リトライを繰り返すのではなく、即座に `val_status = 'error'`, `log_code = 404` を報告し、システムの安全のためにプロセスを「隔離（停止）」させる。

■ 2026-04-04 アップデート: Roleベース管理への移行とプロセス管理の強化

【アーキテクチャの変更】
1. デバイス識別子のRole（役割）ベース化
   - 従来ハードウェアインターフェース名（vst_type: usb, pi等）に依存していた識別を、論理的な役割名（role: cam_main, cam_sub等）へ完全移行。
   - DB（node_configs）の識別キーを role に統一し、HubとNode間のMQTT通信におけるTopicやJSONペイロードも role ベースでルーティングする仕様に変更。

2. コマンド処理の非同期化とステータス分離
   - node_commands: Hubからのコマンドの「ライフサイクル（未処理 -> acknowledged -> completed / error）」を厳密に管理する役割へ特化。
   - node_status_current: 各Unit（カメラ等）が自身の「現在の物理状態（idle, starting, streaming）」を自律的に報告する役割へ特化。
   - baseクラス（vst_base）にて、self.ref_cmd_id を用いて受領したコマンドIDを保持し、処理完了時に node_commands を確実に更新するフローを整備。

3. ゾンビプロセス対策とクリーンアップの徹底
   - Managerおよび各Unitの終了処理を見直し。シグナル（SIGTERM等）受信時に各カメラのストリーミングスレッドやサブプロセスを確実に kill・join する仕組みを実装。
   - 終了時のエラーログが消滅し、安全なシャットダウンが可能になった。

【現在の課題とNext Action】
1. DB連携時のデータ長エラー（1406: Data too long）と例外処理の修正
   - db_bridge等のログ出力処理における未定義変数（logger等）の修正。
   - ステータス更新時に予期せぬ長文が渡されている箇所の特定と、DB更新時の例外ハンドリングの強化。この例外によりコマンドが 'acknowledged' で停止している問題の解消。

2. MJPEGストリーミングの配信不具合の解消
   - ブラウザでの受信時に、MIMEヘッダ（multipart/x-mixed-replace）は到達しているが、画像データが正しく認識されず「Document (0.2KB)」として処理されてしまう問題の調査。
   - Node側の rpicam-vid の出力パイプと、Hub側（wmp_stream_rx.py）のパース処理におけるデータ欠落・境界線（boundary）処理の見直し。

3. 副作用エラーの修正
   - Roleベース移行に伴い発生している sns_move, sw_stream ユニットの初期化エラー（引数不足など）の修正。


1. 関数の引数渡しの厳格化 (Strict Kwargs)

  課題: Pythonの「暗黙の引数解釈」が原因で、意図しないカラムにJSONデータが注入された（1406エラー）。

  規約追加: VSTユニットから vst_base.py のメソッド（update_status, send_response 等）を呼ぶ際は、必ず val_status="idle" のように 「キーワード付き引数」 で呼び出すことをマニフェストに明記し、データの混入を防ぐ。

2. テーブルごとの役割再定義 (log_msg vs log_ext)

  課題: node_commands（命令履歴）と node_status_current（状態保持）で、メッセージを入れるカラムの使い分けが曖昧になっていた。

  規約追加: node_commands には人間が読むための結果概要（log_msg）を保存し、node_status_current 等の生データ領域には詳細なJSONデータ（log_ext / env_json）を保存するという「文字数と用途の分離」を徹底する。

3. 映像ストリームのロバスト性向上

  課題: MJPEGのマーカー（FF D8）を単純検索するだけでは、メタデータ（サムネイル等）に騙される。

  規約追加: 野外等の不安定なパケット環境に対応するため、受信・切り出しロジックは「開始と終了」のペアではなく、「次の開始」を確認してから切り出すというフェイルセーフな設計を標準とする。

1. コマンド・ライフサイクルの厳格化 (Command State Strictness)

  - 定義: コマンドは必ず created → sent → acknowledged → completed または error の終端ステータスに到達しなければならない。

  - 実装ルール: サブプロセスを起動する際は、必ず起動直後の生死判定（wait(timeout)）を行い、クラッシュ時は例外を握りつぶさずに error としてDBを更新（finalize_command）し、トランザクションを完了させること。

2. ペイロードサイズのヒューリスティック評価 (Payload Size Heuristics)

  - 定義: バイナリストリーム（MJPEG等）のパースにおいて、マーカー（FFD8等）の単純検索のみに依存しない。

  - 実装ルール: メタデータ（EXIFサムネイル等）による誤検知を防ぐため、切り出したフレームが「期待される最低サイズ（例: 動画フレームなら5KB以上）」を満たしているかを必ず検証してから配信処理へ回すこと。


DB Schema Integrity:
  completed_at カラムからは DEFAULT CURRENT_TIMESTAMP や ON UPDATE を除外し、Pythonコード側で「本当に処理が完了/失敗した瞬間」に明示的に時刻をセットする設計を徹底する。

State Protection Rule:
  DBのステータス更新時、acknowledged は created/sent 状態からのみ移行を許可し、すでに completed や error になっているレコードを上書き（ダウングレード）してはならない。
  SQL例: UPDATE node_commands SET val_status='acknowledged' WHERE id=1203 AND val_status NOT IN ('completed', 'error');


  ## WES 2026: コマンド実行および状態遷移規格 (Standard for Command Execution & State Transition)

### 1. コマンド・レスポンス・サイクル
ノードが Hub から `vst_control` 命令を受信した場合、以下の 3 段階でレスポンスを返さなければならない。

| 段階 | ステータス (val_status) | 役割 |
| :--- | :--- | :--- |
| **Step 1: ACK** | `acknowledged` | 命令の物理的受領を報告。メインマネージャーが即座に返却する。 |
| **Step 2: EXEC** | `starting` / `stopping` | 内部処理（スレッド起動、HW初期化）を開始。DBの現在状態を更新する。 |
| **Step 3: FINAL** | `completed` / `error` | **動作の成否が確定した時点**で最終報告を行う。 |

### 2. 状態遷移の厳密定義 (node_status_current)
ユニットの状態遷移は、以下のフローを厳守すること。特に「成功の確証」が得られるまでステータスを `streaming` 等へ移行してはならない。

1.  **Idle**: 待機状態。
2.  **Starting**: 初期化中。プロセス起動やHWのオープンを試行している期間。
3.  **Streaming**: 正常稼働中。**「最初のデータパケットが送出された」**ことをもってこの状態に遷移する。
4.  **Error**: 異常発生。`Starting` 中の失敗、または `Streaming` 中のプロセス停止時に遷移する。

### 3. エラーハンドリング条項
- 起動コマンド実行時、HWの不在等でプロセスが即死した場合は、コマンドの最終ステータスを `error` (log_code: 500系) として返却しなければならない。
- `STOP` 命令は、現在の物理状態に関わらず、最終的に必ず `idle` 状態へ着地させ、`completed` を返却しなければならない（二重停止の許容）。