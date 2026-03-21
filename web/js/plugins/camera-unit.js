/**
 * CameraUnit: WES (WildLink Event Standard) 対応版
 * 役割: 映像配信コマンドの送信、およびMQTTイベント(stream_ready)受信による映像表示
 */
class CameraUnit {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        this.name = conf.vst_role_name; 
        
        const params = conf.val_params || {};
        this.streamHost = params.host || window.location.hostname; 
        this.streamPort = "8080"; 
        this.retryCount = 0;
        this.isWaitingReady = false; // Readyイベント待ちフラグ
    }

    /**
     * WES標準メソッド: VstManagerからイベントが転送される
     */
    onEvent(data) {
        console.log(`[CameraUnit:${this.name}] Event received:`, data.event);

        if (data.event === 'stream_ready') {
            // Python側で映像受信が確認された！
            const content = document.getElementById(`content-${this.name}`);
            if (content) {
                this.isWaitingReady = false;
                this.retryCount = 0; // リセットして開始
                this.ensureStream(content);
            }
        } else if (data.event === 'stream_stop') {
            this.removeStream();
        }
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

    /**
     * 定期ポーリング（バックアップ）用
     */
    update(unitData) {
        const el = document.getElementById(`plugin-${this.name}`);
        const disp = document.getElementById(`disp-${this.name}`);
        const content = document.getElementById(`content-${this.name}`);
        
        if (!el || !disp || !content) return;

        const status = (unitData.val_status || "IDLE").toUpperCase();
        disp.innerText = status;

        if (status === 'STREAMING' || status === 'SUCCESS') {
            el.classList.add('u3');
            // Ready待ちでなく、まだ画像がない場合のみ、念のためチェック
            if (!this.isWaitingReady && !document.getElementById(`view-${this.name}`)) {
                this.ensureStream(content);
            }
        } else {
            el.classList.remove('u3');
            this.removeStream();
        }
    }

    /**
     * 映像エレメントの生成と接続
     */
    ensureStream(container) {
        let img = document.getElementById(`view-${this.name}`);
        const buildUrl = () => `http://${this.streamHost}:${this.streamPort}/stream/${this.name}?t=${Date.now()}`;

        if (!img) {
            console.log(`[${this.name}] Initializing stream view...`);
            img = document.createElement('img');
            img.id = `view-${this.name}`;
            img.style.width = "100%";
            img.className = "camera-stream";
            
            img.onerror = () => {
                // MQTTがあればリトライは最小限で済むはずだが、保険として残す
                if (this.retryCount < 5) {
                    this.retryCount++;
                    console.warn(`[${this.name}] Stream connection failed. (Attempt ${this.retryCount})`);
                    setTimeout(() => {
                        const currentImg = document.getElementById(`view-${this.name}`);
                        if (currentImg) currentImg.src = buildUrl();
                    }, 2000);
                }
            };

            img.src = buildUrl();
            container.prepend(img);
            document.getElementById(`disp-${this.name}`).style.fontSize = "0.7rem";
        }
    }

    removeStream() {
        const img = document.getElementById(`view-${this.name}`);
        if (img) {
            img.src = ""; 
            img.remove();
            console.log(`[${this.name}] Stream view removed.`);
        }
        this.retryCount = 0;
        this.isWaitingReady = false;
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
            formData.append('cmd_json', JSON.stringify({ 
                "role": role, 
                "action": action, 
                "act_run": (action === 'start') 
            }));

            const res = await fetch('send_cmd.php', { method: 'POST', body: formData });
            const data = await res.json();
            
            const track = async () => {
                const check = await fetch(`get_command_status.php?id=${data.command_id}`);
                const status = await check.json();
                
                if (status.val_status === 'success') {
                    btn.innerText = "SUCCESS";
                    btn.style.backgroundColor = "#28a745";
                    
                    if (action === 'start') {
                        // 💡 Nodeが受理した。ここからWES(Readyイベント)を待つモードに入る
                        this.isWaitingReady = true; 
                        console.log(`[${this.name}] Command accepted. Waiting for WES 'stream_ready'...`);
                    } else {
                        this.removeStream();
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

// Window登録
window.CameraUnit = CameraUnit;