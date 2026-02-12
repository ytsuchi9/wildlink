import subprocess
import os
import sys

class WildLinkUnit:
    def __init__(self, config):
        # 規約に基づき config から取得
        self.val_name = config.get("val_name", "camera")
        self.hw_pin = config.get("hw_pin", "/dev/video0")
        self.val_res = config.get("val_res", "640x480")
        self.val_fps = config.get("val_fps", 10)
        
        # 規約変更: act_strobe -> act_stream
        self.act_stream = config.get("act_stream", False)
        
        self.log_msg = "Idle"
        self.process = None

    def start_wmp_tx(self):
        """WMP送信スクリプトをサブプロセスで起動"""
        if self.process: return
        
        # 実行スクリプトと同じディレクトリにある wmp_stream_tx.py を指定
        script_dir = os.path.dirname(os.path.abspath(__file__))
        tx_script = os.path.join(script_dir, "wmp_stream_tx.py")
        
        # 実行 (shell=False の方が制御しやすいためリスト形式で渡す)
        self.process = subprocess.Popen(["python3", tx_script])
        self.log_msg = "WMP Streaming"
        print(f"[{self.val_name}] WMP TX Process Started.")

    def stop_wmp_tx(self):
        """プロセスを終了"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
        self.log_msg = "Idle"
        print(f"[{self.val_name}] WMP TX Process Stopped.")

    def update(self):
        # act_stream の状態でプロセスを管理
        if self.act_stream:
            if not self.process:
                self.start_wmp_tx()
            return {"val_status": "streaming", "log_msg": self.log_msg}
        else:
            if self.process:
                self.stop_wmp_tx()
            return {"val_status": "idle", "log_msg": self.log_msg}


# --- (既存の WildLinkUnit クラスの定義の下に追加) 強制起動---

if __name__ == "__main__":
    import time

    # テスト用のダミー設定
    test_config = {
        "val_name": "TestCamera",
        "hw_pin": "/dev/video0",
        "act_stream": True  # 最初から配信オンにする
    }

    print("--- Unit Test Mode ---")
    camera = WildLinkUnit(test_config)

    try:
        while True:
            # updateメソッドを呼び出してプロセスを維持
            status = camera.update()
            # print(f"Current Status: {status}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n--- Stopping Test ---")
        camera.act_stream = False
        camera.update()
        print("Done.")