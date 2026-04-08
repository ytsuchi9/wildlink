/**
 * CameraUnit: WES 2026 Pro-Reactive Edition
 */
class CameraUnit {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        this.name = conf.vst_role_name; 
        
        const params = conf.val_params || {};
        // Hub設定: .env や DB から渡されることを想定
        this.streamHost = params.hub_ip || window.location.hostname; 
        this.streamPort = params.mjpeg_port || "8080"; 
        
        this.retryCount = 0;
        this.keepOpen = false; // 🌟 配信停止時にウィンドウを維持するか
    }

    /**
     * WES標準イベントハンドラ (MQTT経由で MainManager が受信し、ここへ配送される)
     */
    onEvent(data) {
        console.log(`[CameraUnit:${this.name}] MQTT Event: ${data.event}`, data);

        switch (data.event) {
            case 'status_changed':
                // 🌟 ステータス変化（starting/streaming/error 等）に即座に反応
                this.updateUIStatusByCode(data.val_status, data.log_code);
                break;

            case 'stream_ready':
                // 🌟 Hubがパケット受信を完了した瞬間にキックされる
                console.log(`[${this.name}] Stream ready signal received.`);
                const content = document.getElementById(`content-${this.name}`);
                if (content) this.ensureStream(content);
                break;

            case 'stream_lost':
                // 🌟 無信号検知時の処理
                if (!this.keepOpen) {
                    this.removeStream();
                } else {
                    this.updateUIStatus("SIGNAL LOST", "#6c757d");
                }
                break;

            case 'stream_error':
                this.updateUIStatus("DEVICE ERROR", "#dc3545");
                this.removeStream();
                break;
        }
    }

    initUI() {
        const ctrl = document.getElementById(`controls-${this.name}`);
        if (!ctrl) return;
        
        // 🌟 UIの強化: Keep Open スイッチの追加
        ctrl.innerHTML = `
            <div class="d-flex flex-column gap-2">
                <div class="btn-group w-100">
                    <button class="btn btn-sm btn-outline-primary btn-start">START</button>
                    <button class="btn btn-sm btn-outline-secondary btn-stop">STOP</button>
                </div>
                <div class="form-check form-switch small">
                    <input class="form-check-input check-keep" type="checkbox" id="keep-${this.name}">
                    <label class="form-check-label text-muted" for="keep-${this.name}">Keep Window Open</label>
                </div>
            </div>
        `;
        
        const btnStart = ctrl.querySelector('.btn-start');
        const btnStop = ctrl.querySelector('.btn-stop');
        const chkKeep = ctrl.querySelector('.check-keep');

        btnStart.onclick = (e) => this.sendCmd('start', e);
        btnStop.onclick = (e) => this.sendCmd('stop', e);
        chkKeep.onchange = (e) => { this.keepOpen = e.target.checked; };
    }

    /**
     * DBポーリング結果との同期（MQTTが届かない場合のセーフティネット）
     */
    update(unitData) {
        const el = document.getElementById(`plugin-${this.name}`);
        const disp = document.getElementById(`disp-${this.name}`);
        
        if (!el || !disp) return;

        const status = (unitData.val_status || "idle").toLowerCase();
        
        // すでに表示中なら、ポーリングで何度も ensureStream するのを防ぐ
        if (status === 'streaming') {
            el.classList.add('u-active');
            disp.innerText = "STREAMING";
            disp.style.color = "#28a745";
        } else if (status === 'error') {
            el.classList.add('u-error');
            disp.innerText = "ERROR";
        } else {
            el.classList.remove('u-active', 'u-error');
            disp.innerText = status.toUpperCase();
        }
    }

    /**
     * ステータスコードに基づいたUI表現の即時更新
     */
    updateUIStatusByCode(status, code) {
        const disp = document.getElementById(`disp-${this.name}`);
        if (!disp) return;

        const statusMap = {
            "starting":  { text: "STARTING...", color: "#ffc107" },
            "streaming": { text: "STREAMING",   color: "#28a745" },
            "idle":      { text: "IDLE",        color: "#6c757d" },
            "error":     { text: "ERROR",       color: "#dc3545" }
        };

        const config = statusMap[status] || { text: status.toUpperCase(), color: "#000" };
        disp.innerText = config.text;
        disp.style.color = config.color;

        // 🌟 streaming になった瞬間の枠の強調
        const el = document.getElementById(`plugin-${this.name}`);
        if (el) {
            status === 'streaming' ? el.classList.add('u-active') : el.classList.remove('u-active');
        }
    }

    ensureStream(container) {
        let img = document.getElementById(`view-${this.name}`);
        const buildUrl = () => `http://${this.streamHost}:${this.streamPort}/stream/${this.name}?t=${Date.now()}`;

        if (!img) {
            img = document.createElement('img');
            img.id = `view-${this.name}`;
            img.style.width = "100%";
            img.className = "camera-stream img-fluid rounded border border-success";
            
            img.onerror = () => {
                if (this.retryCount < 5) {
                    this.retryCount++;
                    setTimeout(() => { if (img) img.src = buildUrl(); }, 1000);
                }
            };

            img.src = buildUrl();
            container.innerHTML = ''; 
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
    }

    /**
     * コマンド送信 (変更なし)
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

            await fetch('api/send_cmd.php', { method: 'POST', body: formData });
            
            // 🌟 ここでの「追跡(track)」は不要になるかもしれません。
            // なぜならHub/NodeからのMQTT status_changed イベントでボタン状態が勝手に変わるからです。
            // 今回はボタンの無効化解除のためだけに残します。
            setTimeout(() => { btn.disabled = false; btn.innerText = originalText; }, 800);
        } catch (e) { 
            console.error("Command send failed:", e);
            btn.innerText = "ERR";
            btn.disabled = false;
        }
    }
}

window.CameraUnit = CameraUnit;