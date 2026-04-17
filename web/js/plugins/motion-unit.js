/**
 * WES 2026: MotionUnit (9.5-inch Half Rack Style)
 * 完全イベント駆動モデル: 操作はAPIへ送信するのみ。UIの更新はMQTTの受信をトリガーとする。
 */
class MotionUnit extends VstUnitBase {
    constructor(conf, manager) {
        super(conf, manager);
        this.roleName = conf.vst_role_name;

        // UI内部の保持状態
        this.val_enabled = (conf.val_enabled === true || parseInt(conf.val_enabled) === 1);
        this.act_rec = (conf.act_rec === true || parseInt(conf.act_rec) === 1);
        this.val_interval = parseFloat(conf.val_interval || 15.0);

        this.soundEnabled = false;
        this.selectedSound = "beep";
        this.sounds = {
            beep: "https://actions.google.com/sounds/v1/alarms/beep_short.ogg"
        };
        this.lastDetectTime = "---";
    }

    initUI() {
        const content = document.getElementById(`content-${this.roleName}`);
        if (!content) return;

        // リセットボタンを追加、デザインを整理
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

                <div class="d-flex gap-1 mt-1">
                    <button class="btn btn-warning btn-sm py-1 font-monospace" id="btn-reset-${this.roleName}" style="font-size:0.65rem; width:40px;" title="Reset to Default">
                        <i class="fas fa-undo"></i>
                    </button>
                    <button class="btn btn-primary btn-sm flex-grow-1 py-1 font-monospace" id="btn-apply-${this.roleName}" style="font-size:0.65rem;">
                        <i class="fas fa-terminal me-1"></i> APPLY CONFIG
                    </button>
                </div>
            </div>
        `;

        this.updateVisualState();

        document.getElementById(`btn-apply-${this.roleName}`).onclick = () => this.applySettings();
        document.getElementById(`btn-reset-${this.roleName}`).onclick = () => this.resetSettings();
        document.getElementById(`snd-sw-${this.roleName}`).onchange = (e) => this.soundEnabled = e.target.checked;
        
        // スイッチを操作した際は見た目だけ即座に変える(体感速度のため)が、DB確定までは未完了
        document.getElementById(`en-sw-${this.roleName}`).onchange = () => this.updateVisualState();
    }

    updateVisualState() {
        const isEnabled = document.getElementById(`en-sw-${this.roleName}`).checked;
        const pluginEl = document.getElementById(`plugin-${this.roleName}`);
        const ledEl    = document.getElementById(`led-${this.roleName}`);
        const statEl   = document.getElementById(`stat-${this.roleName}`);
        const display  = document.getElementById(`display-${this.roleName}`);

        if (isEnabled) {
            if (pluginEl) pluginEl.classList.remove('unit-disabled');
            if (ledEl) ledEl.className = 'status-led led-on';
            if (statEl && statEl.innerText !== "DETECTED") { 
                statEl.innerText = "SCANNING"; 
                statEl.style.color = "var(--accent-green)"; 
            }
            if (display && display.style.boxShadow === "none") display.style.background = "#0a1a0a";
        } else {
            if (pluginEl) pluginEl.classList.add('unit-disabled');
            if (ledEl) ledEl.className = 'status-led led-off';
            if (statEl) { 
                statEl.innerText = "PAUSED"; 
                statEl.style.color = "#555"; 
            }
            if (display) display.style.background = "#111";
        }
    }

    async applySettings() {
        const btn = document.getElementById(`btn-apply-${this.roleName}`);
        const isEnabled = document.getElementById(`en-sw-${this.roleName}`).checked;
        const isRec     = document.getElementById(`rec-sw-${this.roleName}`).checked;
        const interval  = parseFloat(document.getElementById(`int-val-${this.roleName}`).value);

        btn.disabled = true;
        btn.innerText = "SAVING...";

        try {
            const formData = new URLSearchParams();
            formData.append('sys_id', this.manager.nodeId);
            formData.append('cmd_type', 'update_config');
            formData.append('cmd_json', JSON.stringify({
                role: this.roleName,
                val_enabled: isEnabled ? 1 : 0,
                act_rec: isRec ? 1 : 0,
                val_interval: interval
            }));

            await fetch('api/send_cmd.php', { method: 'POST', body: formData });
            // ※ ここではthis.val_enabled等は上書きしない。MQTTからの完了通知で書き換える。
        } catch (e) {
            btn.classList.replace('btn-primary', 'btn-danger');
            btn.innerText = "ERROR";
            setTimeout(() => { btn.classList.replace('btn-danger', 'btn-primary'); btn.innerText = "APPLY CONFIG"; btn.disabled = false; }, 2000);
        }
    }

    async resetSettings() {
        const btn = document.getElementById(`btn-reset-${this.roleName}`);
        if(!confirm("Restore default settings for this unit?")) return;
        
        btn.disabled = true;
        try {
            const formData = new URLSearchParams();
            formData.append('sys_id', this.manager.nodeId);
            formData.append('cmd_type', 'reset_config'); // 新設のHub用コマンド
            formData.append('cmd_json', JSON.stringify({ role: this.roleName }));
            await fetch('api/send_cmd.php', { method: 'POST', body: formData });
        } catch (e) {
            console.error(e);
        } finally {
            setTimeout(() => { btn.disabled = false; }, 2000);
        }
    }

    /**
     * 🌟 新規：NodeからMQTTで状態が報告された際に呼ばれる (WES 2026 真実同期)
     */
    update(data) {
        // cmd_status が completed、かつ自身のロールに関する更新であればUIに反映
        if (data.cmd_status === 'completed' && data.log_ext) {
            const ext = data.log_ext;
            
            // 値の適用
            if (ext.val_enabled !== undefined) {
                this.val_enabled = (ext.val_enabled === 1 || ext.val_enabled === true);
                document.getElementById(`en-sw-${this.roleName}`).checked = this.val_enabled;
            }
            if (ext.act_rec !== undefined) {
                this.act_rec = (ext.act_rec === 1 || ext.act_rec === true);
                document.getElementById(`rec-sw-${this.roleName}`).checked = this.act_rec;
            }
            if (ext.val_interval !== undefined) {
                this.val_interval = ext.val_interval;
                document.getElementById(`int-val-${this.roleName}`).value = this.val_interval;
            }

            this.updateVisualState();

            // APPLYボタンの成功状態リセット
            const btn = document.getElementById(`btn-apply-${this.roleName}`);
            if (btn && btn.disabled) {
                btn.classList.replace('btn-primary', 'btn-success');
                btn.innerHTML = `<i class="fas fa-check me-1"></i> VERIFIED!`;
                setTimeout(() => {
                    btn.classList.replace('btn-success', 'btn-primary');
                    btn.innerHTML = `<i class="fas fa-terminal me-1"></i> APPLY CONFIG`;
                    btn.disabled = false;
                }, 2000);
            }
        }
    }

    onEvent(data) {
        if (!this.val_enabled) return;

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

VstManager.registerPlugin('motion', MotionUnit);