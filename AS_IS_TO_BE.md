2026/02/20

1. WildLink 開発史（開発年表）
チャットの流れと、仕様の変遷を辿った歴史です。
時期
フェーズ
主要なトピックと変化
1月前半
黎明期
4画面camviewerの試作。単体スクリプトでのカメラ制御とPHPによるアップロード。
1月後半
構造模索
MQTTの導入。Pi2をハブ、PiZeroをエッジとする構成の検討。.envによる環境管理開始。
2月初頭
標準化開始
/opt/wildlink へのディレクトリ集約。「命名規約（sys_, env_等）」の策定。
2/11〜13
DB主導型への転換
重要：「ソースを書き換えずにDBで挙動を変える」方針を決定。node_configsテーブルの設計。
2/14〜17
WMPとVSTの誕生
WildLink Media Pipe (WMP) 仕様策定。Virtual Sensor/Task (VST) 構造による動的ロードの実装。
2/18〜20
統合と課題噴出
main_manager.py による統括。名前の不整合（pi vs camera）や、古い受信スクリプトの混在が課題に。


2. 現存コード解析・整理一覧
ディレクトリごとに、各ファイルの役割と今後の進退を整理しました。
【Common】（心臓部：最重要）
ファイル名
役割・機能
連携先
今後の方向
wmp_core.py
映像伝送（WMP）の基底クラス
vst_camera, wmp_stream_rx
存続（基盤）
vst_base.py
全てのVSTユニットの親クラス
node/vst_*.py
存続（必須）
db_bridge.py
DB接続の隠蔽・土管化。
main_manager.py
存続（推奨）。将来的にAPI化の窓口。

【Node / Units】（Pi Zero側：実行部）
ファイル名
役割・機能
連携先
今後の方向
main_manager.py
司令塔。VSTをロードし周期実行
node_configs (DB), VST類
存続（中核）
vst_camera.py
最新のカメラ制御ユニット
wmp_core.py
存続。vst_camera_v1は廃止。
vst_sys_monitor.py
CPU温度や電圧等のシステム監視
main_manager.py
存続
vst_bmp280.py 等
各種物理センサー制御
main_manager.py
存続（必要に応じて作成）
test_transmitter.py
単体テスト用送信
なし
削除検討（main_managerで完結させる）
unit_camera.py
旧世代のカメラコード
なし
廃止（vst_camera.pyへ統合済）

【Hub】（Pi 2側：受信・管理部）
ファイル名
役割・機能
連携先
今後の方向
hub_manager.py
MQTTを購読し、DBへ自動仕分け
MQTT, MySQL
存続（中核）
wmp_stream_rx.py
UDP映像を受信しMJPEG配信
camviewer.html
存続。wmp_image_rx等は廃止。
mqtt_to_db.py
旧世代のDB保存スクリプト
なし
廃止（hub_managerへ統合）

【Web】（ユーザーインターフェース）
ファイル名
役割・機能
連携先
今後の方向
camviewer.html
動的パネル生成型の監視画面
get_node_status.php
存続（主力UI）
db_config.php
DB接続の共通設定
全てのPHP
存続（現在の.env読込方式を堅持）
get_node_config.php
ノードが必要なVST情報を取得
main_manager.py
存続（重要）
admin.php / index.php
旧世代の管理画面
なし
整理対象。camviewerへ機能を寄せる。


3. 名前の不整合チェック（要注意ポイント）
解析の結果、以下の不整合が「動かない」原因の火種になっています。
デバイス名:
DBの vst_type: pi または usb
コード内の出力: camera と名乗っている箇所がある
対策: ユニット名（キー名）は必ずDBの vst_type を参照して動的に決めるよう main_manager.py を徹底する。
ディレクトリ構成:
設計書上の config/ ディレクトリが、実際には node/ 直下の config.json になっていたりする。
対策: .env を含む設定系は /opt/wildlink/ 直下または config/ に集約する。

4. 今後の開発に向けた「黄金律」の再定義
ブレないための3つの約束を記憶しました。
「DBが絶対」: 挙動を変えるときはコードではなくDBを叩く。
「VST以外の単体駆動禁止」: センサー追加は必ず vst_*.py 形式で作る。
「WMPによる映像一元化」: 独自のソケット通信は作らず、wmp_core を通す。

現状の「歪み」を解消するための整理案

1. 開発トピックの変遷（タイムライン）
これまでの歩みを整理しました。まさに今が「初期実装」から「スケーラブルな構造」への脱皮期間です。
時期
トピック
到達点と課題
1月
直感的なカメラ配信
PHPとShellで強引に動かす段階。拡張性が課題。
2月初頭
MQTT & DB導入
データの流れを整理開始。命名規則を策定。
2/13頃
VST & WMP構想
「設定をDBから拾う」 という現在の根幹ロジックが誕生。
2/17頃
main_manager 実装
各種VSTを統合管理。しかしDBの vst_type とコード内の名前が不一致のまま連結。
2/20(今)
全体統合と整理
「名前の不整合」 と 「旧コードの混在」 を解消し、一本化するフェーズ。


2. DBから見た「名前の不整合」の正体
node_commands テーブルのデータを見て、不整合の原因が特定できました。
現象: cmd_type が camera になっている行が多いが、cmd_json の中身は {"hw_target":"pi", ...} となっている。
不整合:
DBの device_catalog では、名前は pi または usb です。
しかし、コマンド発行側（UI）が camera という名前を cmd_type に入れてしまっています。
さらに、コマンドの中身に hw_target という別の名前キーを持たせてしまっています。
【解決の方針】
「camera」という曖昧な名前は廃止し、vst_type（pi, usb, pir）を主キーとして、すべての通信を統一します。

3. コード整理・廃止・存続の提案
現在の /opt/wildlink 内にあるファイルを、今後「使うべきか」「消すべきか」で分類しました。
A. 今後利用・強化すべき（Core & VST）
これらは統合システムの中心となります。
Common: wmp_core.py, vst_base.py, db_bridge.py
これらは「部品」なので、変更せず使い回す。
Node: main_manager.py, vst_camera.py, vst_sys_monitor.py
vst_camera.py は pi と usb の両方に対応できる「汎用カメラVST」へ昇華させます。
Web: camviewer.html, get_node_config.php, get_node_status.php, send_cmd.php
send_cmd.php を「vst_type を指定して送る」形に修正します。
B. 廃止・アーカイブすべき（旧世代・単体テスト用）
これらが残っていると、どれが正解か分からなくなります。
Node/Units: unit_camera.py, wmp_image_tx.py, wmp_stream_tx.py
これらは vst_camera.py に機能が内包されました。
Hub: mqtt_to_db.py, unit_hub_rx.py, wmp_image_rx.py
hub_manager.py または wmp_stream_rx.py に統合済みです。
Web: start_cam.php, admin.php, upload.php
これらは初期の「直接起動方式」の名残です。

4. 設計の「ブレ」を直すための具体策（記憶用）
今後の開発で私が守るべき、整理された設計ルールです。
コマンドの統一:
node_commands の cmd_type には必ず vst_type (例: pi) を入れる。
cmd_json の中身はシンプルに {"act_run": true} 等にする（hw_target は不要。cmd_type で判別できるため）。
動的ローディングの徹底:
main_manager.py が get_node_config.php から取得した vst_type を、そのままインスタンス名にする。
これにより、PiZero側で camera という名前をハードコードする必要がなくなります。
WMPストリームURLの動的化:
device_catalog または node_configs の val_params にストリーム先のポート番号やパスを持たせ、UI側でそれを組み立てる。

次のステップ：クリーンアップ作戦
もしよろしければ、次回の作業で以下を一緒に行いませんか？
物理的な整理: old_version/ ディレクトリを作り、不要なファイルを移動して視界をクリアにする。
Namingの一貫性修正: vst_camera.py 内で、自分が pi なのか usb なのかを DB から受け取った名前で振る舞うように微調整する。
UIのコマンド発行修正: camviewer.html から送るコマンドを、DBの vst_type に準拠させる。
整理後の「新生WildLink」の構造（イメージ）
整理が終わると、全体の流れは以下の**「DBを中心とした綺麗な三角形」**に収束するはずです。
DB (Single Source of Truth)
設定（node_configs）と命令（node_commands）を一括管理。
Node (PiZero / main_manager.py)
DBから「君のユニット名は pi だよ」と言われたら、その名前でステータスを送り、その名前宛ての命令を待機する。
UI (Web / camviewer.html)
DBから「このノードには pi と usb があるよ」と教えられたら、それに応じたボタンを作る。

次回への備え
物理的な整理が終わった段階で、次は以下の**「コード内の名寄せ」**に着手しましょう。
vst_camera.py の中で camera と名乗っている箇所を、インスタンス生成時の name（pi や usb）を使うように変更。
camviewer.html の JS ロジックで、hw_target という独自キーを使わず、cmd_type に直接 vst_type を乗せるように修正。
今までは「pi (CSI接続)か usb (USB接続)か」という接続インターフェース名で呼んでいましたが、これを機に**「役割名（Role Name）」**で管理する方向にシフトしませんか？
提案：vst_type を「接続名」から「役割名」へ
例えば、以下のようにDBの vst_type を定義し直すイメージです。
cam_main（メインカメラ：現在は pi）
cam_sub（サブカメラ：現在は usb）
cam_rear（後方カメラ）
こうすることで、コード側には以下のようなメリットが生まれます：
ハードウェアの隠蔽: 将来、メインカメラをUSB接続の高性能カメラに変更しても、DBの vst_module を vst_camera に、val_params の中身（/dev/video0 など）を書き換えるだけで、UI（ボタン名など）やロジックを変更せずに済みます。
不整合の解消: 「コードでは camera と呼びたいのに、DBが pi なので困る」という問題が、「DBもコードも cam_main と呼ぶ」ことで完全に一致します。
具体的な変更イメージ
node_configs テーブルの vst_type を以下のように書き換える運用です。
vst_type: cam_main
val_params: {"hw_driver": "pi", "val_res": "640x480"}
vst_type: cam_sub
val_params: {"hw_driver": "usb", "hw_path": "/dev/video1"}
こうすれば、main_manager.py は「俺は cam_main を担当する vst_camera インスタンスを作るぞ」と動くことができ、UIも「cam_main ボタン」を作れば良くなります。
いかがでしょうか？「接続方法」ではなく「何のカメラか」という役割で名前を決めると、今後の拡張がぐっと楽になります。
