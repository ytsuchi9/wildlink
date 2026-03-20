// クラス定義
class CameraUnit {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        this.name = conf.vst_role_name; 
        
        const params = conf.val_params || {};
        this.streamHost = params.host || window.location.hostname; 
        this.streamPort = "8080"; 
        this.retryCount = 0;
    }

    initUI() {
        const ctrl = document.getElementById(`controls-${this.name}`);
        if (!ctrl) return;
        
        ctrl.innerHTML = `
            <button class="btn-control btn-start">STREAM START</button>
            <button class="btn-control btn-stop">STREAM STOP</button>
        `;
        
        const btnStart = ctrl.querySelector('.btn-start');
        const btnStop = ctrl.querySelector('.btn-stop');

        btnStart.onclick = (e) => this.sendCmd(this.manager.nodeId, this.name, 'start', e);
        btnStop.onclick = (e) => this.sendCmd(this.manager.nodeId, this.name, 'stop', e);
    }

    update(unitData) {
        const el = document.getElementById(`plugin-${this.name}`);
        const disp = document.getElementById(`disp-${this.name}`);
        const content = document.getElementById(`content-${this.name}`);
        
        if (!el || !disp || !content) return;

        const isStreaming = (unitData.val_status === 'streaming' || unitData.val_status === 'success');
        disp.innerText = (unitData.val_status || "IDLE").toUpperCase();

        if (isStreaming) {
            el.classList.add('u3'); 
            this.ensureStream(content);
        } else {
            el.classList.remove('u3');
            this.removeStream(content);
        }
    }

    ensureStream(container) {
        let img = document.getElementById(`view-${this.name}`);
        const buildUrl = () => `http://${this.streamHost}:${this.streamPort}/stream/${this.name}?t=${Date.now()}`;

        if (!img) {
            console.log(`[${this.name}] Creating stream element...`);
            img = document.createElement('img');
            img.id = `view-${this.name}`;
            img.style.width = "100%";
            img.className = "camera-stream";
            
            img.onerror = () => {
                // 💡 映像が出ない(黒い)場合は、1.5秒おきに最大5回リトライする
                if (this.retryCount < 10) {
                    this.retryCount++;
                    const delay = 2000; // 2秒おき
                    console.warn(`[${this.name}] Stream not ready (Attempt ${this.retryCount}). Retrying...`);
                    setTimeout(() => {
                        if (document.getElementById(`view-${this.name}`)) {
                            img.src = buildUrl();
                        }
                    }, 1500);
                }
            };

            img.src = buildUrl();
            container.prepend(img);
            document.getElementById(`disp-${this.name}`).style.fontSize = "0.7rem";
        }
    }

    removeStream(container) {
        const img = document.getElementById(`view-${this.name}`);
        if (img) {
            img.src = ""; 
            img.remove();
        }
        this.retryCount = 0; // リセット
        const disp = document.getElementById(`disp-${this.name}`);
        if (disp) disp.style.fontSize = "1.1rem";
    }

    async sendCmd(nodeId, role, action, event) {
        const btn = event.target;
        const originalText = btn.innerText;
        const originalBg = btn.style.backgroundColor;

        btn.disabled = true;
        btn.innerText = "SENDING...";

        try {
            const formData = new URLSearchParams();
            formData.append('sys_id', nodeId); 
            formData.append('cmd_type', 'vst_control');
            formData.append('cmd_json', JSON.stringify({ "role": role, "action": action, "act_run": (action === 'start') }));

            const res = await fetch('send_cmd.php', { method: 'POST', body: formData });
            const data = await res.json();
            
            const track = async () => {
                const check = await fetch(`get_command_status.php?id=${data.command_id}`);
                const status = await check.json();
                
                if (status.val_status === 'success') {
                    btn.innerText = "SUCCESS";
                    btn.style.backgroundColor = "#28a745";
                    
                    // 💡 SUCCESSが出た＝Node側が起動完了したので、ここで映像リクエストを開始
                    if (action === 'start') {
                        this.retryCount = 0;
                        const content = document.getElementById(`content-${this.name}`);
                        if (content) this.ensureStream(content);
                    }

                    setTimeout(() => this.constructor.resetBtn(btn, originalText, originalBg), 2000);
                } else if (status.val_status === 'error') {
                    btn.innerText = "FAILED";
                    btn.style.backgroundColor = "#dc3545";
                    setTimeout(() => this.constructor.resetBtn(btn, originalText, originalBg), 3000);
                } else {
                    setTimeout(track, 800);
                }
            };
            track();
        } catch (e) { 
            this.constructor.resetBtn(btn, "ERROR", "#dc3545");
        }
    }

    static resetBtn(btn, text, bg) {
        btn.disabled = false;
        btn.innerText = text;
        btn.style.backgroundColor = bg;
    }
}

// 💡 画像1の「Class not found」対策：即座にwindowに登録し、マネージャーに通知する
window.CameraUnit = CameraUnit;
if (window.VstManager && typeof window.VstManager.onPluginReady === 'function') {
    window.VstManager.onPluginReady('CameraUnit');
}