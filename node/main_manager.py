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
        self.last_heartbeat = 0
        self.heartbeat_interval = 30 # 30秒ごと
        
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

    def sync_local_config(self):
        """DBから設定を読み取り、ローカルのJSONファイルと同期・保存する"""
        local_path = os.path.join(project_root, "local_config.json")
        
        # 1. DBから最新の設定を取得
        remote_configs = self.db.fetch_node_config(self.node_id)
        
        if remote_configs:
            print(f"🔄 [Sync] Fetched config from DB. Saving to {local_path}...")
            # 2. ローカルに保存 (キャッシュ)
            try:
                with open(local_path, "w") as f:
                    json.dump(remote_configs, f, indent=4, default=str)
                return remote_configs
            except Exception as e:
                print(f"❌ [Sync] Failed to save local config: {e}")
                return remote_configs
        else:
            # 3. オフライン時はローカルから読み込み
            if os.path.exists(local_path):
                print(f"⚠️ [Sync] Offline mode. Loading from local cache...")
                with open(local_path, "r") as f:
                    return json.load(f)
            return None

    def setup_subscription(self):
        """MQTTの命令待ち受けトピックを登録"""
        cmd_topic = f"node/cmd/{self.node_id}"
        self.mqtt.client.subscribe(cmd_topic)
        self.mqtt.client.on_message = self.on_mqtt_message
        print(f"📥 Subscribed to {cmd_topic}")

    def on_mqtt_message(self, client, userdata, msg):
        """外部からのMQTT命令を各ユニットに振り分け + Ack更新"""
        try:
            payload = json.loads(msg.payload.decode())
            target = payload.get("target")
            cmd_id = payload.get("cmd_id") # DB側で発行されたコマンドIDを想定

            # 1. Ack更新 (受け取ったよ)
            if cmd_id:
                self.db.update_command_status(cmd_id, status="acked")

            if target in self.units:
                self.units[target].control(payload)
                
                # 2. Complete更新 (実行完了したよ)
                if cmd_id:
                    self.db.update_command_status(cmd_id, status="completed")
            
        except Exception as e:
            print(f"❌ MQTT Message Error: {e}")

    def setup(self):
        """DBから設定を読み込みユニットを生成"""
        configs = self.sync_local_config()
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
        
        # 1. イベント発生源のユニットを取得
        source_unit = self.units.get(source_role)
        if not source_unit:
            return

        # 2. センサー検知時の連動ロジック
        if event_type == "motion_detected":
            # DBの val_params からターゲットを取得（未設定なら cam_main をデフォルトに）
            target_role = source_unit.params.get("act_target", "cam_main")
            # 停止までの時間を取得（デフォルト30秒）
            duration = source_unit.params.get("val_interval", 30)

            if target_role in self.units:
                print(f"🎥 Motion detected! Starting {target_role} for {duration}s...")
                
                # ターゲットのカメラを起動
                self.units[target_role].control({"act_run": True})
                
                # 指定秒後に停止するタイマー
                threading.Timer(
                    duration, 
                    self.units[target_role].control, 
                    args=[{"act_run": False}]
                ).start()
            else:
                print(f"⚠️ Target unit '{target_role}' not found.")

    def send_heartbeat(self):
        """DBの生存状態を更新"""
        now = time.time()
        if now - self.last_heartbeat > self.heartbeat_interval:
            print("💓 Heartbeat: Updating node status...")
            # nodesテーブルの last_seen を現在時刻に、statusをonlineに
            self.db.update_node_heartbeat(self.node_id, status="online")
            self.last_heartbeat = now

    def run(self):
        print(f"🚀 Node {self.node_id} 稼働開始...")
        try:
            while True:
                self.send_heartbeat() # ★ここを追加
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