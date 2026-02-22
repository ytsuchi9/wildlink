import sys
import os
import json
import time
import threading

# ワーニング抑制
os.environ['GPIOZERO_PIN_FACTORY'] = 'rpigpio'

# パス解決
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
        self.mqtt = None
        
        # MQTTの初期化
        try:
            host = os.getenv('MQTT_BROKER') or "192.168.1.102"
            self.mqtt = MQTTClient(host, node_id) 
            if self.mqtt.connect():
                print(f"📡 MQTT Connected to {host}")
                # 命令待ち受けの設定
                self.setup_subscription()
            else:
                print(f"⚠️ MQTT Connection failed")
        except Exception as e:
            print(f"⚠️ MQTT Initialization failed: {e}")

    def setup_subscription(self):
        """MQTTの命令待ち受けトピックを登録"""
        cmd_topic = f"node/cmd/{self.node_id}"
        self.mqtt.client.subscribe(cmd_topic)
        self.mqtt.client.on_message = self.on_mqtt_message
        print(f"📥 Subscribed to {cmd_topic}")

    def on_mqtt_message(self, client, userdata, msg):
        """外部からのMQTT命令を各ユニットに振り分ける"""
        try:
            payload = json.loads(msg.payload.decode())
            target = payload.get("target")
            print(f"📩 MQTT Command for {target}: {payload}") # ターゲットを表示

            if target in self.units:
                print(f"🎯 Calling control() on {target}") # 呼び出し確認
                self.units[target].control(payload)
            else:
                print(f"⚠️ Target unit '{target}' not found.")
        except Exception as e:
            print(f"❌ MQTT Message Error: {e}")

    def setup(self):
        """DBから設定を読み込みユニットを生成"""
        configs = self.db.fetch_node_config(self.node_id)
        if not configs:
            print(f"⚠️ No config found for {self.node_id}.")
            return

        for cfg in configs:
            role = cfg['vst_type']
            module_name = cfg['vst_module']
            class_name = f"VST_{cfg['vst_class']}" # VST_Camera 等
            params = cfg['val_params']

            try:
                module = __import__(module_name)
                vst_class = getattr(module, class_name)
                
                # インスタンス生成（selfを渡して相互参照可能に）
                unit = vst_class(role, params, self.mqtt)
                unit.manager = self 
                self.units[role] = unit
                print(f"✅ [{role}] 起動完了 ({module_name})")
            except Exception as e:
                print(f"❌ [{role}] 起動失敗: {e}")

    def on_event(self, source_role, event_type):
        """ユニット内部からのイベント通知（センサー検知など）"""
        print(f"🔔 Event: {source_role} -> {event_type}")
        
        # 連動ロジック: sns_move が反応したら cam_main を開始
        if source_role == "sns_move" and event_type == "motion_detected":
            if "cam_main" in self.units:
                print("🎥 Motion detected! Starting cam_main for 30s...")
                self.units["cam_main"].control({"act_run": True})
                # 30秒後に停止するタイマー
                threading.Timer(30, self.units["cam_main"].control, args=[{"act_run": False}]).start()

    def run(self):
        print(f"🚀 Node {self.node_id} 稼働開始...")
        try:
            while True:
                for unit in self.units.values():
                    if hasattr(unit, 'poll'):
                        unit.poll()
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n🛑 停止中...")
            if self.mqtt: self.mqtt.disconnect()

if __name__ == "__main__":
    manager = MainManager("node_001")
    manager.setup()
    manager.run()