import os
from dotenv import load_dotenv

# 1. まず環境変数を読み込む（相対パスの維持）
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

# 2. その後にロガーを生成する
from logger_config import get_logger
logger = get_logger("config_loader")

# システム全体の識別子を確定
# 優先順位: OS環境変数 > .env > デフォルト
SYS_ID = os.getenv("SYS_ID") or os.getenv("NODE_ID") or "node_001"
MQTT_BROKER = os.getenv("MQTT_BROKER") or "localhost"
# .env等から読み込む。設定がなければ "wildlink" をデフォルトにする
MQTT_PREFIX = os.getenv("MQTT_PREFIX", "wildlink")
GROUP_ID    = os.getenv("GROUP_ID", "home_internal")

# getattr(config_loader, 'GROUP_ID', 'home_internal')

# --- [WES 2026 追加項目] ---
# Hub（映像/データ受信側）のIPアドレス。動画配信の宛先として必須。
HUB_IP = os.getenv("HUB_IP") or "127.0.0.1"
# --------------------------

logger.info(f"🚀 [Config] System ID: {SYS_ID}, HUB IP: {HUB_IP}", extra={"log_code": 100})