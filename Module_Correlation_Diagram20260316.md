WildLink 2026 モジュール相関図
現在、システムは以下の 4つの階層 で整理され、wildlink_core.php を心臓部として完全に統合されています。

1. ユーザーインターフェース層 (UI)
    sys_monitor.php: 全体監視ダッシュボード。全ノードの死活・バイタルを俯瞰。
    camviewer.html: 各ノードの「ラックコンソール」。特定ノードの映像確認と制御を担当。
    js/vst-manager.js: UIとAPIの仲介役。
    js/plugins/*.js: カメラやセンサーの各ユニット専用ロジック。
    css/vst-rack.css: コンソールのデザイン定義。

2. API / 通信層 (PHP)
    api_status_cards.php: sys_monitor.php 用の全ノードサマリーを配信。
    get_node_status.php: camviewer.html 用の特定ノード詳細・ユニット状態を配信。
    api_logs.php: システム全体、または特定ノードのログを配信。
    send_cmd.php: UIからのコマンドを node_commands テーブルへキューイング。
    get_command_status.php: 送信したコマンドの成否（pending → success）を追跡。
    get_node_config.php: ノードに搭載されているユニット構成（VST構成）を配信。

3. コア / 共通基盤層
    wildlink_core.php: 【最重要】 唯一のDB接続・設定管理。PDO/mysqli の提供、およびバイタル取得などの共通メソッドを保持。
    .env: DBパスワードや接続先などの機密情報を保持。

4. データ層
    MySQL (WildLink DB): 全ての状態・設定・履歴を管理。
    MJPEG Bridge (Port 8080): カメラ映像の配信実体。