import sys
import os
import json
import time

# 1. ワーニング抑制 (gpiozeroのバックエンドを明示的に指定)
os.environ['GPIOZERO_PIN_FACTORY'] = 'rpigpio'

# 2. パス解決: プロジェクトルート (/opt/wildlink) を最優先で追加
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from common.db_bridge import DBBridge
    from common.mqtt_client import MQTTClient
except ImportError as e:
    print(f"❌ Import Error: {e}")
    sys.exit(1)

class MainManager:
    def __init__(self, node_id):
        self.node_id = node_id
        self.db = DBBridge()
        self.units = {}
        
        # MQTTの初期化
        try:
            # .envがない場合は環境に合わせてIPを直書きまたはgetenv
            host = os.getenv('MQTT_BROKER') or "192.168.1.102"
            self.mqtt = MQTTClient(host, node_id) 
            if self.mqtt.connect():
                print(f"📡 MQTT Connected to {host}")
            else:
                print(f"⚠️ MQTT Connection failed")
        except Exception as e:
            print(f"⚠️ MQTT Initialization failed: {e}")
            self.mqtt = None

    def setup(self):
        """DBから設定を読み込み、ユニットを動的に生成する"""
        configs = self.db.fetch_node_config(self.node_id)
        if not configs:
            print(f"⚠️ No active configuration found for {self.node_id}.")
            return

        for cfg in configs:
            role = cfg['vst_type']
            module_name = cfg['vst_module']
            class_name = cfg['vst_class']
            params = cfg['val_params']

            try:
                # nodeフォルダ内のモジュールをインポート
                module = __import__(module_name)
                vst_class = getattr(module, f"VST_{class_name}")
                
                # インスタンス生成
                self.units[role] = vst_class(role, params, self.mqtt)
                print(f"✅ [{role}] を起動しました ({module_name})")

            except Exception as e:
                print(f"❌ [{role}] の起動失敗: {e}")

    def run(self):
        if not self.units:
            print("❌ 稼働ユニットなし。")
            return

        print(f"🚀 Node {self.node_id} 稼働開始...")
        try:
            while True:
                for unit in self.units.values():
                    if hasattr(unit, 'poll'):
                        unit.poll()
                time.sleep(0.1) 
        except KeyboardInterrupt:
            print("\n🛑 停止中...")
            if self.mqtt:
                self.mqtt.disconnect()

if __name__ == "__main__":
    manager = MainManager("node_001")
    manager.setup()
    manager.run()