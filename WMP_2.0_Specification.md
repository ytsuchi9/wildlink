WildLink システム構成仕様書 (WMP 2.0版)
1. 設計思想 (Core Philosophy)
    ハードウェア抽象化: pi や usb といった接続名ではなく、cam_main や cam_sub といった 「役割名 (Role Name)」 で制御する。

    実態ベースの同期: 命令の受理 (node_commands) ではなく、パケットの到達実態 (wmp_stream_rx) をもって node_status_current の状態を確定させる。
    
    ハイブリッド通信: 指示系統には MQTT、データ配信には UDP/WMP を使用する。

2. システムアーキテクチャ
    2.1. 構成コンポーネント
        Edge Node (PiZero)

        main_manager.py: MQTT 命令の待受、各 VST ユニットの管理。

        vst_camera.py: 指定された役割名に基づき、UDP で WMP パケットを送信。

        Hub (RasPi2/Center)

        wmp_stream_rx.py: UDP 受信ブリッジ。パケット受信時に DB を更新し、HTTP MJPEG として配信。

        Database (MariaDB): wildlink_db。システム全体の「真実の状態」を保持。

        Frontend (Viewer)

        camviewer.html: DB の node_status_current をポーリングし、UI を動的に変更。

    2.2. データの流れ (Data Flow)
        【配信開始シーケンス】
        [CMD] Viewer が node_commands に開始命令を INSERT。

        [MQTT] Hub が命令を検知し、MQTT で PiZero へ転送。

        [EXEC] PiZero (MainManager) が該当ユニット (cam_main等) を起動。

        [ACK] PiZero が MQTT で「受理成功」を返信（node_commands が success になる）。

        [SYNC] Hub (StreamRX) が UDP パケットを受信。直ちに node_status_current を streaming に更新。

        [VIEW] Viewer が DB の streaming 状態を検知し、画面を拡大して動画を表示。

        【停止・タイムアウトシーケンス】
        [STOP] 停止命令により PiZero がパケット送信を停止。

        [T.O.] Hub (StreamRX) が 3秒間パケット途絶を検知。

        [SYNC] Hub が node_status_current を idle に更新。

        [VIEW] Viewer が DB の idle 状態を検知し、画面を縮小・リセット。

3. データベース構造 (DB Schema)
    3.1. node_status_current (動的状態管理)
        実働状態を管理する最重要テーブル。

        sys_id: ノードID (例: node_001)

        vst_type: 役割名 (例: cam_main, cam_sub)

        val_status: 現在の状態 (idle, streaming, error)

        updated_at: 最終更新時刻

    3.2. node_configs (静的設定管理)
        各ユニットの物理・論理設定。

        vst_type: 役割名

        vst_role_name: 表示用名称

        val_params: ポート番号や解像度等の JSON

4. 命名規則 (Naming Conventions)
    4.1. 接頭辞
    hw_: 物理固定設定 (hw_bus_addr, hw_driver)

    val_: 動作設定・状態 (val_enabled, val_status, val_params)

    sys_: 本体状態 (sys_cpu_t, sys_id)

    net_: 通信関連 (net_ip, net_port)

    4.2. カメラ役割名
    cam_main: メインカメラ (旧 pi)

    cam_sub: サブカメラ (旧 usb)

    cam_rear: 後方カメラ

5. 開発上の注意点
    DB接続: Hub 側の StreamStore では、オーバーヘッド削減のため DB セッションを再利用し、切断時は自動再接続を行う。

    排他制御: 複数カメラの同時起動に対応するため、Hub 側のポート処理はスレッドごとに独立させる。