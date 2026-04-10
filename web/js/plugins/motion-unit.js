/**
 * =========================================================
 * WildLink Event Standard (WES) 2026 準拠
 * コンポーネント: MotionUnit Plugin (人感センサーUI)
 * 役割:
 * 1. センサー状態のリアルタイム表示 (MQTTイベント駆動)
 * 2. Nodeに対する動作設定パッチ (val_enabled, val_interval, act_rec) の生成と送信
 * 3. ブラウザローカルでの通知音再生
 * =========================================================
 */
/**
 * WES 2026: MotionUnit (9.5-inch Half Rack Style)
 */
class MotionUnit extends VstUnitBase {
    constructor(conf, manager) {
        super(conf, manager);
        this.roleName = conf.vst_role_name;

        // --- 状態の優先順位（真実の反映） ---
        // MQTTの boolean と DBの 1/0 両方に対応
        this.val_enabled = (conf.val_enabled === true || parseInt(conf.val_enabled) === 1);
        this.act_rec = (conf.act_rec === true || parseInt(conf.act_rec) === 1);
        this.val_interval = parseFloat(conf.val_interval || 15.0);

        this.soundEnabled = false;
        this.selectedSound = "beep";
        this.sounds = {
            beep: "https://actions.google.com/sounds/v1/alarms/beep_short.ogg",
            alarm: "https://actions.google.com/sounds/v1/alarms/alarm_clock.ogg"
        };
        this.lastDetectTime = "---";
    }

    initUI() {
        const content = document.getElementById(`content-${this.roleName}`);
        if (!content) return;

        // 19インチ・ハーフラック風の高密度レイアウト
        content.innerHTML = `
            <div class="vst-rack-panel d-flex flex-column gap-1 p-1">
                <div class="d-flex justify-content-between align-items-center px-2 py-1 bg-black border border-secondary rounded-top">
                    <div class="d-flex align-items-center gap-2">
                        <div id="led-${this.roleName}" class="status-led ${this.val_enabled ? 'led-on' : 'led-off'}"></div>
                        <span class="fw-bold text-uppercase" style="font-size:0.6rem; color:#888; letter-spacing:1px;">Unit Power</span>
                    </div>
                    <div class="form-check form-switch m-0">
                        <input class="form-check-input" type="checkbox" id="en-sw-${this.roleName}" ${this.val_enabled ? 'checked' : ''}>
                    </div>
                </div>

                <div class="d-flex gap-1">
                    <div id="display-${this.roleName}" class="rack-display flex-grow-1 d-flex flex-column align-items-center justify-content-center border border-secondary bg-dark" style="height:90px;">
                        <div id="icon-${this.roleName}" class="mb-1" style="font-size: 1.8rem; color: var(--text-dim); transition: 0.2s;">
                            <i class="fas fa-walking"></i>
                        </div>
                        <div id="stat-${this.roleName}" class="font-monospace fw-bold" style="font-size: 0.65rem;">IDLE</div>
                        <div class="mt-1 opacity-50 font-monospace" id="time-${this.roleName}" style="font-size: 0.55rem;">${this.lastDetectTime}</div>
                    </div>

                    <div class="d-flex flex-column gap-1 bg-black p-1 border border-secondary rounded-end" style="width: 120px;">
                        <div class="rack-param-row">
                            <label style="font-size:0.5rem;">REC DB</label>
                            <input type="checkbox" id="rec-sw-${this.roleName}" ${this.act_rec ? 'checked' : ''} style="transform:scale(0.8);">
                        </div>
                        <div class="rack-param-row">
                            <label style="font-size:0.5rem;">BEEP</label>
                            <input type="checkbox" id="snd-sw-${this.roleName}" style="transform:scale(0.8);">
                        </div>
                        <div class="input-group input-group-sm mt-auto">
                            <span class="input-group-text bg-secondary text-white border-0 p-1" style="font-size:0.5rem;">HOLD</span>
                            <input type="number" id="int-val-${this.roleName}" class="form-control bg-dark text-white border-0 p-0 text-center" style="font-size:0.7rem;" value="${this.val_interval}">
                        </div>
                    </div>
                </div>

                <button class="btn btn-primary btn-sm w-100 py-1 font-monospace" id="btn-apply-${this.roleName}" style="font-size:0.65rem; border-radius:0 0 2px 2px;">
                    <i class="fas fa-terminal me-1"></i> APPLY CONFIG
                </button>
            </div>
        `;

        this.updateVisualState();

        // イベント登録
        document.getElementById(`btn-apply-${this.roleName}`).onclick = () => this.applySettings();
        document.getElementById(`snd-sw-${this.roleName}`).onchange = (e) => this.soundEnabled = e.target.checked;
        document.getElementById(`en-sw-${this.roleName}`).onchange = () => this.updateVisualState();
    }

    /**
     * UIの見た目を現在の val_enabled 状態に合わせて更新する
     */
    updateVisualState() {
        const isEnabled = document.getElementById(`en-sw-${this.roleName}`).checked;
        const pluginEl = document.getElementById(`plugin-${this.roleName}`);
        const ledEl    = document.getElementById(`led-${this.roleName}`);
        const statEl   = document.getElementById(`stat-${this.roleName}`);
        const display  = document.getElementById(`display-${this.roleName}`);

        if (isEnabled) {
            pluginEl.classList.remove('unit-disabled');
            ledEl.className = 'status-led led-on';
            statEl.innerText = "SCANNING";
            statEl.style.color = "var(--accent-green)";
            display.style.background = "#0a1a0a"; // 稼働中っぽいうっすら緑
        } else {
            // Disable時も明るく表示するが、背景をグレーにして「待機感」を出す
            pluginEl.classList.add('unit-disabled');
            ledEl.className = 'status-led led-off';
            statEl.innerText = "PAUSED";
            statEl.style.color = "#555";
            display.style.background = "#111";
        }
    }

    /**
     * システム設定をひとまとめにしてAPI(Hub)へ送信する
     * WES 2026: 設定の差分(パッチ)を cmd_json に格納して投げる
     */
    async applySettings() {
        const btn = document.getElementById(`btn-apply-${this.roleName}`);
        
        // 画面の入力値を取得
        const isEnabled = document.getElementById(`en-sw-${this.roleName}`).checked;
        const isRec     = document.getElementById(`rec-sw-${this.roleName}`).checked;
        const interval  = parseFloat(document.getElementById(`int-val-${this.roleName}`).value);

        btn.disabled = true;
        btn.innerText = "SAVING...";

        try {
            // APIへ送信するフォームデータの構築
            const formData = new URLSearchParams();
            formData.append('sys_id', this.manager.nodeId);
            formData.append('cmd_type', 'update_config');
            
            // 🌟 WESマニフェスト: パッチ形式で cmd_json を構築
            const cmdJson = {
                role: this.roleName,
                val_enabled: isEnabled ? 1 : 0,
                act_rec: isRec ? 1 : 0,
                val_interval: interval
            };
            formData.append('cmd_json', JSON.stringify(cmdJson));

            // 送信
            await fetch('api/send_cmd.php', { method: 'POST', body: formData });
            
            // UI内部状態の更新
            this.val_enabled = isEnabled;
            this.act_rec = isRec;
            this.val_interval = interval;
            
            // 見た目の更新（PAUSED切り替えなど）
            this.updateVisualState();

            // 成功フィードバック
            btn.classList.replace('btn-primary', 'btn-success');
            btn.innerHTML = `<i class="fas fa-check me-1"></i> UPDATED!`;
            setTimeout(() => {
                btn.classList.replace('btn-success', 'btn-primary');
                btn.innerHTML = `<i class="fas fa-upload me-1"></i> APPLY TO NODE`;
                btn.disabled = false;
            }, 2000);

        } catch (e) {
            console.error("[MotionUnit] Failed to apply settings:", e);
            btn.classList.replace('btn-primary', 'btn-danger');
            btn.innerText = "ERROR";
            setTimeout(() => {
                btn.classList.replace('btn-danger', 'btn-primary');
                btn.innerHTML = `<i class="fas fa-upload me-1"></i> APPLY TO NODE`;
                btn.disabled = false;
            }, 2000);
        }
    }

    /**
     * val_enabled (有効/無効) の状態に応じて、パネル全体の見た目とテキストを更新する
     */
    updateVisualState() {
        const ledEl = document.getElementById(`led-${this.roleName}`);
        const statEl = document.getElementById(`stat-${this.roleName}`);
        
        if (this.val_enabled) {
            if (ledEl) ledEl.className = 'status-led led-on';
            if (statEl) { statEl.innerText = "SCANNING"; statEl.style.color = "var(--accent-green)"; }
        } else {
            if (ledEl) ledEl.className = 'status-led led-off';
            if (statEl) { statEl.innerText = "PAUSED"; statEl.style.color = "#555"; }
        }
    }

    /**
     * MQTTからブロードキャストされたイベントを受け取る (VstManagerから呼ばれる)
     * @param {Object} data - 受信したイベントペイロード
     */
    onEvent(data) {
        console.log(`[MotionUnit] Event Received (${this.roleName}):`, data); // 🚀 デバッグログ

        // UI上のスイッチがOFFなら、検知アニメーションをスキップ
        if (!this.val_enabled) {
            console.log("[MotionUnit] Unit is disabled in UI, ignoring event.");
            return;
        }

        if (data.event === 'motion_detected' || data.val_status === 'detected') {
            this.handleDetection(data);
        } else if (data.val_status === 'idle') {
            this.handleReset();
        }
    }

    handleDetection(data) {
        const icon = document.getElementById(`icon-${this.roleName}`);
        const stat = document.getElementById(`stat-${this.roleName}`);
        const timeEl = document.getElementById(`time-${this.roleName}`);
        const display = document.getElementById(`display-${this.roleName}`);

        if (data.env_last_detect) {
            this.lastDetectTime = new Date(data.env_last_detect).toLocaleTimeString('ja-JP');
            if (timeEl) timeEl.innerText = this.lastDetectTime;
        }

        if (icon) { icon.style.color = "var(--accent-red)"; icon.classList.add('vst-blink'); }
        if (stat) { stat.innerText = "DETECTED"; stat.style.color = "var(--accent-red)"; }
        if (display) display.style.boxShadow = "inset 0 0 15px rgba(220,53,69,0.5)";

        if (this.soundEnabled) {
            new Audio(this.sounds[this.selectedSound]).play().catch(() => {});
        }
    }

    handleReset() {
        const icon = document.getElementById(`icon-${this.roleName}`);
        const stat = document.getElementById(`stat-${this.roleName}`);
        const display = document.getElementById(`display-${this.roleName}`);

        if (icon) { icon.style.color = "var(--text-dim)"; icon.classList.remove('vst-blink'); }
        if (stat) { stat.innerText = "SCANNING"; stat.style.color = "var(--accent-green)"; }
        if (display) display.style.boxShadow = "none";
    }
}

// VstManager へプラグインを登録 (これを忘れると初期化されない)
VstManager.registerPlugin('motion', MotionUnit);