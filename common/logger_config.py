import logging
import os
import sys

# 同階層の db_bridge を読み込めるようにする
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from db_bridge import DBBridge

class MySQLHandler(logging.Handler):
    def __init__(self, db_bridge, sys_id, log_type):
        super().__init__()
        self.db = db_bridge
        self.sys_id = sys_id
        self.log_type = log_type

    def emit(self, record):
        try:
            msg = self.format(record)
            self.db.insert_system_log(
                sys_id=self.sys_id,
                log_type=self.log_type,
                level=record.levelname.lower(),
                msg=msg,
                code=getattr(record, 'log_code', 0)
            )
        except Exception:
            self.handleError(record)

def get_logger(module_name):
    # .env から SYS_ID を取得
    sys_id = os.getenv("SYS_ID", "unknown_node")
    db = DBBridge()
    
    # DBからログレベル設定を取得
    db_level_str = db.get_log_level(sys_id).upper()
    level = getattr(logging, db_level_str, logging.INFO)

    logger = logging.getLogger(module_name)
    logger.setLevel(level)

    if not logger.handlers:
        # コンソール
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter('? [%(name)s] %(message)s'))
        logger.addHandler(stream_handler)

        # DB
        db_handler = MySQLHandler(db, sys_id, module_name)
        db_handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(db_handler)

    return logger