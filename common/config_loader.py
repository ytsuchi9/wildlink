import os
from dotenv import load_dotenv

# 1. まず環境変数を読み込む
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

# 2. その後にロガーを生成する
from logger_config import get_logger
logger = get_logger("config_loader")

# システム全体の識別子を確定
# 優先順位: OS環境変数 > .env > デフォルト
SYS_ID = os.getenv("SYS_ID") or os.getenv("NODE_ID") or "node_001"
MQTT_BROKER = os.getenv("MQTT_BROKER") or "localhost"

logger.info(f"🚀 [Config] System ID identified as: {SYS_ID}", extra={"log_code": 100})