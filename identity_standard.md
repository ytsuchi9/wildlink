# WildLink 2026 Role-Based ID 規格書 (Draft)

## 1. 概要
WildLink システムにおける各コンポーネント（ハブ、ノード、個別モジュール）を識別するための命名規則および ID 管理手法を定義する。これにより、分散環境下でのログ追跡、コマンド配送、ステータス同期の確実性を担保する。

---

## 2. ID 命名規則
識別子 `SYS_ID` は以下のフォーマットで定義する。

**`[Type]_[Role]_[Instance]`**

| セクション | 説明 | 例 |
| :--- | :--- | :--- |
| **Type** | 機器の大きな区分 | `hub`, `node` |
| **Role** | そのプロセスの役割 | `mgr` (Manager), `stat` (Status), `ui`, `cam`, `sns` |
| **Instance** | 個体識別番号 | `01`, `02`, `alpha`, `beta` |

### 具体例
- `hub_mgr_01`: ハブ側のメインコマンド配送エンジン
- `hub_ui_main`: ハブ側のWebインターフェース
- `node_001`: エッジノードのマスタープロセス
- `hub_stat_worker`: ログ収集専用のサブプロセス

---

## 3. 環境変数の運用ルール

### 3.1 .env ファイル (機器単位のアイデンティティ)
各ハードウェアのルート（`/opt/wildlink/.env`）に配置する。
その機器の「デフォルト名」を定義する。

```bash
# マシン自体の名前
MACHINE_ID=wild_hub_alpha

# 共通設定
MQTT_BROKER=localhost
DB_HOST=localhost

3.2 実行時オーバーライド (プロセス単位のアイデンティティ)
1つの機器で複数のモジュールを実行する場合、起動コマンドまたはサービス定義（Systemd等）にて SYS_ID を注入する。

コマンド例:

Bash
SYS_ID=hub_stat_01 python3 hub/status_engine.py


4. 実装コードサンプル
今後作成する新しいモジュールでは、以下のパターンを標準とする。

Python モジュール実装

Python

import os
from logger_config import get_logger

# 1. モジュール名の定義
MODULE_NAME = "new_feature_worker"

# 2. ロガーの初期化 (内部で SYS_ID を自動認識)
logger = get_logger(MODULE_NAME)

def main():
    # 実行時に環境変数を取得して利用する場合
    my_identity = os.getenv("SYS_ID") or "unknown_worker"
    logger.info(f"Worker started as {my_identity}")

if __name__ == "__main__":
    main()

Systemd サービス定義例 (/etc/systemd/system/wildlink-xxx.service)

Ini, TOML

[Unit]
Description=WildLink New Feature

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/wildlink
# ここで役割に応じた ID を指定
Environment=SYS_ID=hub_feature_01
ExecStart=/usr/bin/python3 -m hub.new_feature
Restart=always

[Install]
WantedBy=multi-user.target
5. 期待される効果
ログの可視化: 集中ログ管理 (MySQL) において、どのプロセスのログか即座に判別可能。

スケーラビリティ: 同じコードのまま、IDを変えて複数起動するだけで負荷分散や冗長化が可能。

リモートデバッグ: 遠隔地のノードがハブに接続した際、トピックパス（vst/[SYS_ID]/res）に基づいて自動的に識別・登録される。