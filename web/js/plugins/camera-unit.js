class CameraUnit {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        // 2026年仕様: vst_role_name を唯一の識別子にする（cam_main, cam_sub等）
        this.name = conf.vst_role_name; 
        
        const params = conf.val_params || {};
        // ホスト名は基本現在のドメイン。ポートは MJPEG Bridge 標準の 8080
        this.streamHost = params.host || window.location.hostname; 
        this.streamPort = "8080"; 
    }

    // 初期UI構築
    initUI() {
        const ctrl = document.getElementById(`controls-${this.name}`);
        if (!ctrl) return;
        
        // 2026年仕様: ボタン生成とイベントバインド
        ctrl.innerHTML = `
            <button class="btn-control btn-start">STREAM START</button>
            <button class="btn-control btn-stop">STREAM STOP</button>
        `;
        
        const btnStart = ctrl.querySelector('.btn-start');
        const btnStop = ctrl.querySelector('.btn-stop');

        // manager.nodeId を使用してコマンド送信
        btnStart.onclick = (e) => CameraUnit.sendCmd(this.manager.nodeId, this.name, 'start', e);
        btnStop.onclick = (e) => CameraUnit.sendCmd(this.manager.nodeId, this.name, 'stop', e);
    }

    // 状態更新（VstManagerから3秒おきに呼ばれる）
    update(unitData) {
        const el = document.getElementById(`plugin-${this.name}`);
        const disp = document.getElementById(`disp-${this.name}`);
        const content = document.getElementById(`content-${this.name}`);
        
        if (!el || !disp || !content) return;

        // streaming または success の場合に映像を表示
        const isStreaming = (unitData.val_status === 'streaming' || unitData.val_status === 'success');
        disp.innerText = (unitData.val_status || "IDLE").toUpperCase();

        if (isStreaming) {
            el.classList.add('u3'); // アクティブスタイル（CSS側で定義）
            this.ensureStream(content);
        } else {
            el.classList.remove('u3');
            this.removeStream(content);
        }
    }

    ensureStream(container) {
        let img = document.getElementById(`view-${this.name}`);
        
        if (!img) {
            img = document.createElement('img');
            img.id = `view-${this.name}`;
            img.style.width = "100%";
            img.className = "camera-stream";
            
            // 2026規格URL: http://[IP]:8080/stream/[role_name]
            const buildUrl = () => `http://${this.streamHost}:${this.streamPort}/stream/${this.name}?t=${Date.now()}`;

            img.onerror = () => {
                console.warn(`[${this.name}] Stream load error. Retrying...`);
                setTimeout(() => {
                    const currentImg = document.getElementById(`view-${this.name}`);
                    if (currentImg) currentImg.src = buildUrl();
                }, 1500); 
            };

            img.src = buildUrl();
            container.prepend(img);
            document.getElementById(`disp-${this.name}`).style.fontSize = "0.7rem";
        }
    }

    removeStream(container) {
        const img = document.getElementById(`view-${this.name}`);
        if (img) {
            img.src = ""; // 接続を明示的に切断
            img.remove();
        }
        const disp = document.getElementById(`disp-${this.name}`);
        if (disp) disp.style.fontSize = "1.1rem";
    }

    /**
     * コマンド送信静的メソッド
     */
    static async sendCmd(nodeId, role, action, event) {
        const btn = event.target;
        const originalText = btn.innerText;
        const originalBg = btn.style.backgroundColor;

        btn.disabled = true;
        btn.innerText = "SENDING...";

        try {
            const formData = new URLSearchParams();
            formData.append('sys_id', nodeId); 
            formData.append('cmd_type', 'vst_control');

            // 2026年仕様: payloadに role と action を含める
            const cmdData = { 
                "role": role,
                "action": action,
                "act_run": (action === 'start')
            };
            formData.append('cmd_json', JSON.stringify(cmdData));

            const res = await fetch('send_cmd.php', { method: 'POST', body: formData });
            const data = await res.json();
            
            if (data.error) throw new Error(data.error);
            
            const cmdId = data.command_id;

            // コマンドの成否を追跡
            const track = async () => {
                const check = await fetch(`get_command_status.php?id=${cmdId}`);
                const status = await check.json();
                
                if (status.val_status === 'success') {
                    btn.innerText = "SUCCESS";
                    btn.style.backgroundColor = "#28a745";
                    setTimeout(() => CameraUnit.resetBtn(btn, originalText, originalBg), 2000);
                } else if (status.val_status === 'error' || (status.log_code && status.log_code >= 400)) {
                    btn.innerText = "FAILED";
                    btn.style.backgroundColor = "#dc3545";
                    setTimeout(() => CameraUnit.resetBtn(btn, originalText, originalBg), 3000);
                } else {
                    setTimeout(track, 800); // 継続監視
                }
            };
            track();

        } catch (e) { 
            console.error("Command Error:", e);
            btn.innerText = "ERROR";
            setTimeout(() => CameraUnit.resetBtn(btn, originalText, originalBg), 3000);
        }
    }

    static resetBtn(btn, text, bg) {
        btn.disabled = false;
        btn.innerText = text;
        btn.style.backgroundColor = bg;
    }
}
// js/plugins/camera-unit.js の最後に追加
window.CameraUnit = CameraUnit;