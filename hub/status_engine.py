import sys
import os
import time
import json

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common'))
from mqtt_client import MQTTClient
from db_bridge import DBBridge

BROKER = "localhost"

def on_message(client, userdata, msg):
    # 関数が呼ばれるたびに新しいDB接続インスタンスを作る（Unread resultの究極の対策）
    db = DBBridge() 
    
    try:
        topic_parts = msg.topic.split('/')
        node_id = topic_parts[1]
        payload = json.loads(msg.payload.decode())

        # --- A. ノードからのレスポンス (res) 処理 ---
        if topic_parts[2] == "res":
            cmd_id = payload.get("cmd_id")
            val_status = payload.get("val_status")
            if not cmd_id: return
            
            # 【対策1】DBインスタンスを操作ごとに都度生成
            db_cmd = DBBridge()
            
            # 1. まず履歴を更新
            sql_cmd = "UPDATE node_commands SET val_status = %s, log_code = %s, log_msg = %s, res_payload = %s, completed_at = NOW(3) WHERE id = %s"
            db_cmd._execute(sql_cmd, (val_status, payload.get("log_code"), payload.get("log_msg"), json.dumps(payload), cmd_id))
            # 履歴更新用インスタンスをここで明示的に破棄（に等しい処理）
            del db_cmd

            # 2. 成功時のみステータス同期
            if val_status == "success":
                time.sleep(0.1) # データベースの書き込み完了をわずかに待つ
                db_sync = DBBridge() # 【対策2】同期用に「完全に新しい」接続を作る
                
                try:
                    # SELECTを実行
                    res = db_sync._execute("SELECT cmd_json FROM node_commands WHERE id = %s", (cmd_id,))
                    
                    if res and len(res) > 0:
                        raw_json = res[0][0] if isinstance(res[0], (list, tuple)) else res[0]
                        cmd_info = json.loads(raw_json)
                        vst_type = cmd_info.get("target")
                        action = cmd_info.get("action")
                        
                        if vst_type:
                            new_status = 'streaming' if action == 'start' else 'idle'
                            sql_status = """
                                INSERT INTO node_status_current (sys_id, vst_type, val_status)
                                VALUES (%s, %s, %s)
                                ON DUPLICATE KEY UPDATE val_status = VALUES(val_status), updated_at = NOW()
                            """
                            db_sync._execute(sql_status, (node_id, vst_type, new_status))
                            print(f"[{node_id}] ⚡ Status synced: {vst_type} -> {new_status}")
                except Exception as e:
                    print(f"❌ Sync Error: {e}")
                finally:
                    del db_sync # 接続を確実に閉じる

            print(f"[{node_id}] ✅ Command {cmd_id} finished.")

        # --- B. ノードからのレポート (report) 処理 ---
        elif topic_parts[2] == "report":
            sys_mon = payload.get("sys_monitor", {})
            
            # 1. system_logs への保存
            sql_log = "INSERT INTO system_logs (sys_id, log_level, sys_cpu_t, sys_board_t, net_rssi, log_msg) VALUES (%s, %s, %s, %s, %s, %s)"
            db._execute(sql_log, (node_id, "info", sys_mon.get("sys_cpu_t"), sys_mon.get("sys_board_t"), sys_mon.get("net_rssi"), sys_mon.get("log_msg")))

            # 2. node_data への保存
            units_data = payload.get("units", {})
            env_data = {k: v for k, v in sys_mon.items() if k.startswith("env_")}
            
            sql_data = "INSERT INTO node_data (sys_id, env_temp, env_hum, env_pres, env_lux, raw_data) VALUES (%s, %s, %s, %s, %s, %s)"
            db._execute(sql_data, (node_id, env_data.get("env_temp"), env_data.get("env_hum"), env_data.get("env_pres"), env_data.get("env_lux"), json.dumps(units_data)))
            print(f"[{node_id}] 📥 Metrics archived.")

    except Exception as e:
        print(f"❌ Status Engine Error: {e}")
    # 関数の終わりで db インスタンスが破棄され、コネクションも安全にクローズされる

mqtt = MQTTClient(BROKER, "hub_status_engine")
mqtt.client.on_message = on_message
if mqtt.connect():
    mqtt.client.subscribe("vst/+/report")
    mqtt.client.subscribe("vst/+/res")
    print("🚀 WildLink 2026 Status Engine (Config-Sync Mode) started...")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        mqtt.disconnect()