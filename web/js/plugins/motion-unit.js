/**
 * WES 2026: MotionUnit (Inherits VstUnitBase)
 */
class MotionUnit extends VstUnitBase {
    constructor(conf, manager) {
        super(conf, manager);
    }

    initUI() {
        const p = this.conf.val_params || {}; // confから直接初期値を取得
        const interval = p.val_interval || 15.0;
        const recMode  = p.act_rec_mode || 0;
        const isRec    = p.act_rec === 1;
        const isDb     = p.act_db === 1;
        const isLine   = p.act_line === 1;

        const faceCenterHtml = `
            <div class="d-flex align-items-center justify-content-center">
                <i id="icon-${this.roleName}" class="fas fa-walking" style="font-size: 1.2rem; color: var(--text-dim);"></i>
                <span id="stat-${this.roleName}" class="font-monospace fw-bold ms-2" style="font-size: 0.8rem; color: ${this.val_enabled ? 'var(--accent-green)' : '#555'};">
                    ${this.val_enabled ? 'SCANNING' : 'PAUSED'}
                </span>
            </div>
        `;

        // 🌟修正: フォーム部品にBootstrap標準のスタイル(form-control, form-select, bg-dark, text-light)を付与
        const accordionHtml = `
            <div class="row g-2 align-items-center" style="font-size: 0.85rem;">
                <div class="col-12">
                    <label class="form-label text-light mb-1">HOLD (sec)</label>
                    <input type="number" id="int-val-${this.roleName}" class="form-control form-control-sm bg-dark text-light border-secondary vst-input" data-key="val_interval" value="${interval}">
                </div>
                <div class="col-12">
                    <label class="form-label text-light mb-1 mt-1">REC MODE</label>
                    <select id="recmode-${this.roleName}" class="form-select form-select-sm bg-dark text-light border-secondary vst-input" data-key="act_rec_mode">
                        <option value="0" ${recMode == 0 ? 'selected' : ''}>Snapshot</option>
                        <option value="1" ${recMode == 1 ? 'selected' : ''}>Video</option>
                    </select>
                </div>

                <div class="col-12 border-top border-secondary pt-2 mt-2">
                    <div class="d-flex flex-column gap-2">
                        <div class="form-check form-switch m-0">
                            <input class="form-check-input vst-input" type="checkbox" id="rec-sw-${this.roleName}" data-key="act_rec" ${isRec ? 'checked' : ''}>
                            <label class="form-check-label text-light">REC</label>
                        </div>
                        <div class="form-check form-switch m-0">
                            <input class="form-check-input vst-input" type="checkbox" id="db-sw-${this.roleName}" data-key="act_db" ${isDb ? 'checked' : ''}>
                            <label class="form-check-label text-light">DB SAVE</label>
                        </div>
                        <div class="form-check form-switch m-0">
                            <input class="form-check-input vst-input" type="checkbox" id="line-sw-${this.roleName}" data-key="act_line" ${isLine ? 'checked' : ''}>
                            <label class="form-check-label text-light">LINE</label>
                        </div>
                    </div>
                </div>
            </div>
        `;

        this.buildBaseWrapper(faceCenterHtml, accordionHtml);
    }

    updateFaceVisual() {
        const ledEl  = document.getElementById(`led-${this.roleName}`);
        const statEl = document.getElementById(`stat-${this.roleName}`);
        
        if (this.val_enabled) {
            if (ledEl) ledEl.className = 'status-led led-on';
            if (statEl && statEl.innerText !== "DETECTED") { 
                statEl.innerText = "SCANNING"; 
                statEl.style.color = "var(--accent-green)"; 
            }
        } else {
            if (ledEl) ledEl.className = 'status-led led-off';
            if (statEl) { 
                statEl.innerText = "PAUSED"; 
                statEl.style.color = "#555"; 
            }
        }
    }

    async applySettings() {
        const btn = document.getElementById(`btn-apply-${this.roleName}`);
        const originalContent = btn.innerHTML;
        btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> APPLYING`;
        btn.disabled = true;

        try {
            const formData = new URLSearchParams();
            formData.append('sys_id', this.manager.nodeId);
            formData.append('cmd_type', 'update_config');

            const payload = { role: this.roleName };
            document.querySelectorAll(`#content-${this.roleName} .vst-input`).forEach(input => {
                const key = input.getAttribute('data-key');
                if (key) {
                    payload[key] = input.type === 'checkbox' ? (input.checked ? 1 : 0) : parseFloat(input.value);
                }
            });

            formData.append('cmd_json', JSON.stringify(payload));
            await fetch('api/send_cmd.php', { method: 'POST', body: formData });
            
            this.triggerKickDisplay(); 
        } catch (e) {
            console.error("Apply Error:", e);
        } finally {
            btn.innerHTML = originalContent;
            btn.disabled = false;
        }
    }

    update(data) {
        this.updateLCD(data.log_msg, data.log_code, data.log_ext || data.val_params, data.updated_at);

        if (data.log_ext) {
            this.originalConfig = { ...this.originalConfig, ...data.log_ext };
        }
        if (data.val_enabled !== undefined) {
            this.originalConfig.val_enabled = parseInt(data.val_enabled);
            this.val_enabled = (this.originalConfig.val_enabled === 1);
        }

        this.resetSettings(); // ここでDirtyもリセットされる
        this.updateFaceVisual();

        if (data.cmd_status === 'completed' || data.val_status === 'synced') {
            this.triggerKickDisplay();
        }
    }

    onEvent(data) {
        if (!this.val_enabled) return;

        const icon = document.getElementById(`icon-${this.roleName}`);
        const stat = document.getElementById(`stat-${this.roleName}`);

        if (data.event === 'motion_detected' || data.val_status === 'detected') {
            if (icon) { icon.style.color = "var(--accent-red)"; icon.classList.add('vst-blink'); }
            if (stat) { stat.innerText = "DETECTED"; stat.style.color = "var(--accent-red)"; }
            
            this.updateLCD("MOTION DETECTED!", 200, data.log_ext, data.created_at);
            this.triggerKickDisplay();

        } else if (data.val_status === 'idle') {
            if (icon) { icon.style.color = "var(--text-dim)"; icon.classList.remove('vst-blink'); }
            if (stat) { stat.innerText = "SCANNING"; stat.style.color = "var(--accent-green)"; }
        }
    }
}