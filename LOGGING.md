ログの集中管理（DB保存）への移行について、Gitのこれまでのコード解析と、現在のプロジェクト構造から見積もりを行いました。

修正が必要なモジュール数と影響範囲の見積もり

結論から言うと、**主要な修正対象は「5つ」**です。これらの中に点在する print() を logger.info() 等に置き換えていく作業になります。
    モジュール分類  ファイル名（想定）        修正の重み          理由
    共通基盤        common/db_bridge.py     高          ログをDBに書き込む「心臓部」を実装するため。
    Hub側主幹       hub/hub_manager.py      中          指令の送出ログ、エラー検知の保存。
    Hub側エンジン   hub/status_engine.py    中          Nodeからのレスポンスやレポート受信の記録。
    Node側主幹      node/main_manager.py    中          起動、コマンド受信、ハード制御のログ。
    配信制御        hub/wmp_stream_rx.py    低          プロセス起動・終了の記録。

見積もり詳細
    総ファイル数: 5～6ファイル
    修正箇所: 1ファイルあたり 5〜15か所の print 文
    作業の難易度: 低（基本的には機械的な置換です）

効率的な移行ステップ案「すべてのモジュールを作り直す」のは大変そうに聞こえますが、Pythonの logging モジュールの標準的な仕組みを使えば、**「各ファイルの冒頭数行を追加し、printをloggerに変えるだけ」**で済みます。ステップ1：DBBridge にログ書き込み口を作るまず common/db_bridge.py に、system_logs テーブルへガツンと書き込むメソッドを1つ作ります。ステップ2：共通ロガー設定を作るcommon/logger_config.py のようなファイルを作り、そこに「DBに送る設定」と「コンソールに出す設定」をまとめます。ステップ3：各モジュールで読み込む各ファイルの先頭で以下のように宣言します。Pythonfrom common.logger_config import get_logger
logger = get_logger("hub_manager") # モジュール名を指定

# あとは print を logger に変えるだけ
# print("Starting...") -> logger.info("Starting...")
集中管理にすることの最大のメリットセンサーモジュールの作成に専念しやすくなる最大の理由は、**「ブラウザ（WebUI）だけでデバッグが完結する」**ようになるからです。今のデバッグ: HubにSSHしてログを見て、次にNodeにSSHしてログを見て…と行き来が必要。集中管理後: WebUIの「システムログ一覧」を見るだけで、「Nodeが反応したか」「HubがDBを更新したか」が一つのタイムラインで表示されます。


DBの変更 (Migration)

-- nodesテーブルにデバッグレベル設定を追加
ALTER TABLE nodes ADD COLUMN val_log_level VARCHAR(20) DEFAULT 'info' AFTER val_status;

-- system_logsにモジュール名カラムを追加
ALTER TABLE system_logs ADD COLUMN log_type VARCHAR(50) AFTER sys_id;

