/**
 * CameraUnit: WES (WildLink Event Standard) 2026 対応版
 * 役割: 映像配信コマンドの送信、およびMQTT経由のストリーム状態の同期
 */
class CameraUnit {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        this.name = conf.vst_role_name; 
        
        const params = conf.val_params || {};
        // Hub(ストリーム配信元)のホストとポート。デフォルトはHubの8080番
        this.streamHost = params.hub_ip || window.location.hostname; 
        this.streamPort = "8080"; 
        
        this.retryCount = 0;
        this.isWaitingReady = false; 
    }

    /**
     * WES標準イベントハンドラ: MainManager(WS経由)から受信したイベントを処理
     */
    onEvent(data) {
        console.log(`[CameraUnit:${this.name}] Event: ${data.event}`, data);

        switch (data.event) {
            case 'streaming_started':
                // Python(Node)側でキャプチャが開始された
                this.isWaitingReady = false;
                this.retryCount = 0;
                const contentStarted = document.getElementById(`content-${this.name}`);
                if (contentStarted) {
                    this.ensureStream(contentStarted);
                }
                break;

            case 'streaming_stopped':
                // 明示的な停止イベント
                this.removeStream();
                break;

            case 'error':
                // デバイスエラー等
                console.error(`[CameraUnit:${this.name}] Node reported an error:`, data.log_msg);
                this.updateUIStatus("ERROR", "#dc3545");
                this.removeStream();
                break;
        }
    }

    initUI() {
        const ctrl = document.getElementById(`controls-${this.name}`);
        if (!ctrl) return;
        
        ctrl.innerHTML = `
            <div class="btn-group w-100">
                <button class="btn btn-sm btn-outline-primary btn-start">START</button>
                <button class="btn btn-sm btn-outline-secondary btn-stop">STOP</button>
            </div>
        `;
        
        const btnStart = ctrl.querySelector('.btn-start');
        const btnStop = ctrl.querySelector('.btn-stop');

        btnStart.onclick = (e) => this.sendCmd('start', e);
        btnStop.onclick = (e) => this.sendCmd('stop', e);
    }

    /**
     * 定期ポーリング(DB経由)による状態同期のバックアップ
     */
    update(unitData) {
        const el = document.getElementById(`plugin-${this.name}`);
        const disp = document.getElementById(`disp-${this.name}`);
        const content = document.getElementById(`content-${this.name}`);
        
        if (!el || !disp || !content) return;

        const status = (unitData.val_status || "idle").toLowerCase();
        disp.innerText = status.toUpperCase();

        // 状態に基づいたクラス付与（CSSで枠を光らせる等）
        if (status === 'streaming') {
            el.classList.add('u-active'); // ストリーミング中の強調スタイル
            if (!this.isWaitingReady && !document.getElementById(`view-${this.name}`)) {
                this.ensureStream(content);
            }
        } else if (status === 'error') {
            el.classList.add('u-error');
            this.removeStream();
        } else {
            el.classList.remove('u-active', 'u-error');
            this.removeStream();
        }
    }

    /**
     * 映像エレメント(img)の生成。HubのMJPEGリレーに接続する。
     */
    ensureStream(container) {
        let img = document.getElementById(`view-${this.name}`);
        // WES 2026: /stream/{role} の形式でHubへリクエスト
        const buildUrl = () => `http://${this.streamHost}:${this.streamPort}/stream/${this.name}?t=${Date.now()}`;

        if (!img) {
            console.log(`[${this.name}] Connecting to Hub MJPEG stream...`);
            img = document.createElement('img');
            img.id = `view-${this.name}`;
            img.style.width = "100%";
            img.className = "camera-stream img-fluid rounded";
            
            img.onerror = () => {
                if (this.retryCount < 10) {
                    this.retryCount++;
                    const delay = Math.min(this.retryCount * 1000, 5000);
                    console.warn(`[${this.name}] Stream connecting... retry ${this.retryCount}`);
                    setTimeout(() => {
                        const currentImg = document.getElementById(`view-${this.name}`);
                        if (currentImg) currentImg.src = buildUrl();
                    }, delay);
                }
            };

            img.src = buildUrl();
            container.innerHTML = ''; // 既存のプレースホルダーを消去
            container.appendChild(img);
        }
    }

    removeStream() {
        const img = document.getElementById(`view-${this.name}`);
        if (img) {
            img.src = ""; 
            img.remove();
        }
        this.retryCount = 0;
        this.isWaitingReady = false;
    }

    /**
     * UI上のステータス表示を一時的に更新する
     */
    updateUIStatus(text, color) {
        const disp = document.getElementById(`disp-${this.name}`);
        if (disp) {
            disp.innerText = text;
            if (color) disp.style.color = color;
        }
    }

    /**
     * PHP経由でNodeへコマンドを送信
     */
    async sendCmd(action, event) {
        const btn = event.target;
        const originalText = btn.innerText;
        btn.disabled = true;
        btn.innerText = "WAIT...";

        try {
            const formData = new URLSearchParams();
            formData.append('sys_id', this.manager.nodeId); 
            formData.append('cmd_type', 'vst_control');
            formData.append('cmd_json', JSON.stringify({ 
                "role": this.name, 
                "act_run": (action === 'start') 
            }));

            const res = await fetch('api/send_cmd.php', { method: 'POST', body: formData });
            const data = await res.json();
            
            if (!data.command_id) throw new Error("No command ID returned");

            // コマンドが受理されたかDBを追跡
            const track = async () => {
                const check = await fetch(`api/get_command_status.php?id=${data.command_id}`);
                const status = await check.json();
                
                if (status.val_status === 'success') {
                    btn.innerText = "OK";
                    if (action === 'start') {
                        this.isWaitingReady = true; 
                        this.updateUIStatus("CONNECTING...", "#ffc107");
                    }
                    setTimeout(() => { btn.disabled = false; btn.innerText = originalText; }, 1000);
                } else if (status.val_status === 'error') {
                    btn.innerText = "ERR";
                    this.updateUIStatus("CMD FAILED", "#dc3545");
                    setTimeout(() => { btn.disabled = false; btn.innerText = originalText; }, 2000);
                } else {
                    setTimeout(track, 500); // 処理中なら継続
                }
            };
            track();
        } catch (e) { 
            console.error("Command send failed:", e);
            btn.innerText = "ERR";
            btn.disabled = false;
        }
    }
}

// グローバルに登録
window.CameraUnit = CameraUnit;