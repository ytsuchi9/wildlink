import sys
import os
import json
import time
import threading
import RPi.GPIO as GPIO

# パス解決
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from common.db_bridge import DBBridge
from common.mqtt_client import MQTTClient

class MainManager:
    def __init__(self, node_id):
        self.node_id = node_id
        self.db = DBBridge()
        self.units = {}
        self.links = []          
        self.active_timers = {}  
        self.current_config_raw = ""  
        
        # 💡 追加：同期タイミングの管理用
        self.last_sync_time = 0      # 初回実行を確実にするため 0
        self.sync_interval = 30      # 30秒ごとにDBと同期
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_cache_path = os.path.join(base_dir, 'last_config.json')

    def setup_mqtt(self):
        host = os.getenv('MQTT_BROKER') or "192.168.1.102"
        self.mqtt = MQTTClient(host, self.node_id)
        if self.mqtt.connect():
            cmd_topic = f"vst/{self.node_id}/cmd/+" 
            self.mqtt.client.subscribe(cmd_topic)
            self.mqtt.client.on_message = self.on_mqtt_message
            print(f"📡 MQTT Connected & Subscribed to {cmd_topic}")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            target = payload.get("target")
            cmd_id = payload.get("cmd_id")
            res_topic = f"vst/{self.node_id}/res"

            if cmd_id:
                self.mqtt.client.publish(res_topic, json.dumps({"cmd_id": cmd_id, "val_status": "acked"}))

            if target in self.units:
                try:
                    self.units[target].execute_logic(payload) # execute_logicに統一
                    if cmd_id:
                        self.mqtt.client.publish(res_topic, json.dumps({
                            "cmd_id": cmd_id, "val_status": "success", "log_code": 200,
                            "target_status": getattr(self.units[target], 'val_status', 'unknown')
                        }))
                except Exception as unit_e:
                    if cmd_id:
                        self.mqtt.client.publish(res_topic, json.dumps({
                            "cmd_id": cmd_id, "val_status": "error", "log_code": 500, "log_msg": str(unit_e)
                        }))
            elif target == "manager" and payload.get("action") == "reload":
                self.load_and_init_units()

        except Exception as e:
            print(f"❌ [MQTT] Error: {e}")

    def load_and_init_units(self):
        """DBから最新設定を読み込み、キャッシュと比較して変更があれば反映"""
        # 1. DBから最新情報を取得
        new_configs = self.db.fetch_node_config(self.node_id)
        new_links = self.db.fetch_vst_links(self.node_id) # 💡追加：リンク情報
        
        # 2. ネットワークエラー時のフォールバック (DBがNoneの場合)
        if new_configs is None:
            if os.path.exists(self.config_cache_path):
                print("⚠️ [Manager] DB connection failed. Loading from cache...")
                with open(self.config_cache_path, 'r') as f:
                    cached_data = json.load(f)
                    new_configs = cached_data.get("configs", [])
                    new_links = cached_data.get("links", [])
            else:
                return

        # 3. 差分チェック用のデータ構造を作成
        # ユニット構成とリンク設定の両方を一つの辞書にまとめる
        current_data_set = {
            "configs": new_configs,
            "links": new_links
        }
        
        # JSON文字列化して、前回保存した状態と比較
        new_config_raw = json.dumps(current_data_set, sort_keys=True, default=str)
        if new_config_raw == self.current_config_raw:
            return # 変更がなければ何もしない（運用中のストリーミングを止めないため）

        # --- 変更があった場合の処理 ---
        print("🔄 [Manager] Config/Links change detected. Synchronizing...")
        
        # キャッシュの更新
        self.current_config_raw = new_config_raw
        self.links = new_links  # 💡追加：メモリ上のリンク情報を更新
        with open(self.config_cache_path, 'w') as f:
            json.dump(current_data_set, f)
        
        # 4. 既存ユニットの安全な停止
        # タイマーを止めないと、再初期化後に古いタイマーが発動してエラーになる
        for t in self.active_timers.values(): 
            t.cancel()
        self.active_timers.clear()
        
        # 各ユニットのストリーミングやスレッドを停止
        for unit in self.units.values():
            if hasattr(unit, 'stop'): 
                unit.stop()
        self.units.clear()
        
        # GPIOをリセットしてピン競合を防ぐ
        GPIO.cleanup()
        GPIO.setmode(GPIO.BCM)

        # 5. DBの定義に基づいたユニットの再生成
        for cfg in new_configs:
            role = cfg['vst_type']
            cls_name = cfg['vst_class']
            mod_name = cfg.get('vst_module', f"vst_{cls_name.lower()}")
            params = cfg.get('val_params', {})
            
            # 新設計のカラムを辞書にまとめる
            unit_config = {
                "hw_driver": cfg.get("hw_driver"),
                "hw_bus_addr": cfg.get("hw_bus_addr"),
                "vst_role_name": cfg.get("vst_role_name")
            }

            try:
                # 動的インポート
                module = __import__(f"node.{mod_name}", fromlist=[f"VST_{cls_name}"])
                vst_class = getattr(module, f"VST_{cls_name}")
                
                # 新旧クラス互換性チェック
                import inspect
                sig = inspect.signature(vst_class.__init__)
                if 'config' in sig.parameters:
                    # 新しい config 引数対応クラス
                    self.units[role] = vst_class(role, params, self.mqtt, self.on_event, config=unit_config)
                else:
                    # 移行期間用の旧クラス対応
                    self.units[role] = vst_class(role, params, self.mqtt, self.on_event)
                
                print(f"✅ [{role}] Activated ({unit_config['hw_driver']} @ {unit_config['hw_bus_addr']})")
            except Exception as e: 
                print(f"❌ [{role}] Activation failed: {e}")

    def on_event(self, source_role, event_type):
        """
        vst_links に基づいてイベントを配信する
        """
        print(f"🔔 [Event] Source: {source_role} Type: {event_type}")
        
        # メモリ上の links から合致するものを探す
        matched_links = [l for l in self.links if l['source_role'] == source_role]
        
        if not matched_links:
            print(f"⚠️ [Manager] No links found for {source_role}. Ignoring.")
            return

        for link in matched_links:
            target_role = link['target_role']
            duration = link['val_interval']
            
            if target_role in self.units:
                target_unit = self.units[target_role]
                # 現在の状態を取得 (act_run属性がある前提)
                is_active = getattr(target_unit, "act_run", False)
                
                # val_interval が 0 ならトグル、それ以外は一定時間ON
                new_run = not is_active if duration == 0 else True
                
                print(f"➡️ [Route] {source_role} -> {target_role} (Action: {'TOGGLE' if duration == 0 else 'ON'})")
                target_unit.execute_logic({"act_run": new_run})
                
                # タイマー制御 (ONにする場合のみ)
                if target_role in self.active_timers:
                    self.active_timers[target_role].cancel()
                
                if new_run and duration > 0:
                    t = threading.Timer(duration, lambda r=target_role: self.units[r].execute_logic({"act_run": False}))
                    t.daemon = True
                    self.active_timers[target_role] = t
                    t.start()

    def run(self):
        self.setup_mqtt()
        # 💡 MQTTの受信待機スレッドを開始（これがないと on_mqtt_message が呼ばれません）
        self.mqtt.client.loop_start() 
        
        # 初回ロード
        self.load_and_init_units()
        
        try:
            while True:
                now = time.time()
                # 定期同期（ハートビートと設定確認）
                if now - self.last_sync_time > self.sync_interval:
                    self.db.update_node_heartbeat(self.node_id, status="online")
                    self.load_and_init_units() 
                    self.last_sync_time = now
                
                # 各ユニットのポーリング（スイッチのチャタリング防止など）
                for unit in self.units.values():
                    if hasattr(unit, 'poll'): 
                        unit.poll()
                
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n👋 Stopping Manager...")
            self.mqtt.client.loop_stop()
            GPIO.cleanup()

if __name__ == "__main__":
    manager = MainManager("node_001")
    manager.run()