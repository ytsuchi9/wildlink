import paho.mqtt.client as mqtt
import json
import os
import sys
from dotenv import load_dotenv

# --- パス解決 ---
# /opt/wildlink/hub から一つ上の common を参照できるようにする
current_dir = os.path.dirname(os.path.abspath(__file__))
wildlink_root = os.path.dirname(current_dir)
sys.path.append(os.path.join(wildlink_root, "common"))

from db_bridge import DBBridge

# 環境変数の読み込み
load_dotenv(os.path.join(wildlink_root, ".env"))

# 土管（DBBridge）の初期化
bridge = DBBridge(dotenv_path=os.path.join(wildlink_root, ".env"))

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Connected to MQTT Broker")
        # すべてのノードのレスポンスを購読
        client.subscribe("wildlink/+/res")
    else:
        print(f"❌ Connection failed with code {rc}")

def on_message(client, userdata, msg):
    try:
        # トピック例: wildlink/node_001/res
        topic_parts = msg.topic.split('/')
        node_id = topic_parts[1]
        
        payload = json.loads(msg.payload.decode())
        print(f"[*] Received report from {node_id}")

        # 各ユニット（Camera, SysMonitor等）ごとのデータをループ処理
        for unit_name, unit_data in payload.items():
            
            # 1. 命名規則に基づいたデータの仕分け
            # env_ で始まるキーを抽出（環境データ）
            env_data = {k: v for k, v in unit_data.items() if k.startswith('env_')}
            
            # sys_ または net_ で始まるキーを抽出（システム状態データ）
            sys_data = {k: v for k, v in unit_data.items() if k.startswith('sys_') or k.startswith('net_')}

            # 2. sensor_logs への保存
            if env_data:
                sql = """
                    INSERT INTO sensor_logs (sys_id, env_temp, env_hum, raw_data) 
                    VALUES (%s, %s, %s, %s)
                """
                # JSONには他のデータも含まれる可能性があるため unit_data 全体を raw_data に保存
                params = (node_id, env_data.get('env_temp'), env_data.get('env_hum'), json.dumps(unit_data))
                bridge.save_log(sql, params)

            # 3. system_logs への保存
            if sys_data:
                sql = """
                    INSERT INTO system_logs (sys_id, sys_volt, sys_cpu_t, net_rssi, log_msg) 
                    VALUES (%s, %s, %s, %s, %s)
                """
                params = (
                    node_id, 
                    sys_data.get('sys_volt'), 
                    sys_data.get('sys_cpu_t'), 
                    sys_data.get('net_rssi'), 
                    unit_data.get('log_msg', 'Normal')
                )
                bridge.save_log(sql, params)

        # 4. ノードの生存確認（last_seen）を更新
        update_node_sql = "UPDATE nodes SET last_seen = CURRENT_TIMESTAMP WHERE sys_id = %s"
        bridge.save_log(update_node_sql, (node_id,))

    except Exception as e:
        print(f"❌ Error processing message: {e}")

def main():
    # MQTTクライアントの設定
    # 注意: Callback API v2 (最新) に対応させています
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    client.on_connect = on_connect
    client.on_message = on_message

    # Broker (自分自身) に接続
    try:
        client.connect("127.0.0.1", 1883, 60)
        print("🚀 Hub Manager is starting...")
        client.loop_forever()
    except Exception as e:
        print(f"❌ Could not connect to MQTT Broker: {e}")

if __name__ == "__main__":
    main()