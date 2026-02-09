import subprocess
import signal
import os

def is_ffmpeg_running():
    """FFmpegが既にこのユニット経由で動いているか確認"""
    try:
        # pgrepを使って自分のデバイスを叩いているffmpegを探す
        result = subprocess.run(["pgrep", "-f", "ffmpeg.*video1"], capture_output=True)
        return result.returncode == 0
    except:
        return False

def get_data(configs):
    action = configs.get("act_line", "stop")
    device = configs.get("hw_driver", "/dev/video1")
    dest_ip = configs.get("net_ip", "192.168.0.102")
    dest_port = configs.get("net_port", 5000)
    
    running = is_ffmpeg_running()

    if action == "start":
        if not running:
            # 修正版：mpeg4にエンコードして送信（これならPi 2が確実に映像と認識します）
            cmd = (
            f"ffmpeg -hide_banner -loglevel error "
            f"-f v4l2 -video_size 320x240 -i {device} "
            f"-c:v mpeg4 -vtag xvid -q:v 10 -f mpegts "
            f"udp://{dest_ip}:{dest_port}?pkt_size=1316 &"
            )
            os.system(cmd)
            return True, {"log_msg": "New stream process launched"}
        else:
            return True, {"log_msg": "Stream already active"}

    elif action == "stop" and running:
        os.system(f"pkill -f 'ffmpeg.*{device}'")
        return True, {"log_msg": "Stream stopped"}

    return True, {}