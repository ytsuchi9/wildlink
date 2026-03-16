レイヤー,   モジュール名,               依存先 / 参照DB,                        主要な変数・役割,               状態
共通基盤,   wildlink_core.php,          .env / 全テーブル,                      "$pdo, $mysqli / DB接続と環境設定の集約",稼働中
API,        api_logs.php,system_logs,   システム全体の最新ログ50件をJSON出力,   整理済
API,        api_status_cards.php,       "nodes, system_logs",                                               各ノードの sys_status とバイタルを出力,整理済
API,        get_node_status.php,        nodes,特定ノードの詳細状態（温度・RSSI等）を取得,                      
監視UI,     sys_monitor.php,            上記API群,システム全体の「司令塔」。JSで5秒毎に更新,                    稼働中
操作UI,     camviewer.html,             get_node_config.php,カメラ映像表示。NODE_ID を元にユニット構成を生成,   



