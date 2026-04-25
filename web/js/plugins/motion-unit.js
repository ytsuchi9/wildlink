/**
 * WES 2026: MotionUnit (Inherits VstUnitBase)
 * V17 Rack Layout - High Density 3-Line Edition
 */
class MotionUnit extends VstUnitBase {
    constructor(conf, manager) {
        super(conf, manager);
    }

    // --- UI 構築 (HTML) ---
    renderFaceCenter() {
        const locName = this.conf.loc_name || 'LOCAL';
        
        return `
            <div class="unit-header-bar" style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div style="font-size:3cqi; font-weight:bold; overflow:hidden; white-space:nowrap; text-overflow:ellipsis;">
                    ${this.conf.vst_description}
                </div>
                <div style="text-align:right; line-height:1.1; flex-shrink:0;">
                    <div style="font-family:monospace; font-size:1.6cqi; color:#ccc;">${this.sysId} / ${this.roleName}</div>
                    <div style="font-family:monospace; font-size:1.4cqi; color:#888;">${locName}</div>
                </div>
            </div>

            <div style="display:flex; align-items:center; margin-top:0.3cqi; overflow:hidden; white-space:nowrap;">
                <span style="font-family:monospace; font-size:2cqi; color:#888; margin-right:0.5cqi;">STAT:</span>
                <span id="stat-${this.roleName}" style="font-family:monospace; font-size:2.2cqi; color:var(--accent-green); font-weight:bold; min-width:8cqi;">
                    ${this.conf.val_status}
                </span>
                
                <div style="margin-left:0.5cqi; display:flex; align-items:center;">
                    <span class="ind-led" id="ind-rec-${this.roleName}">REC</span>
                    <span class="ind-led" id="ind-db-${this.roleName}">DB</span>
                    <span class="ind-led" id="ind-line-${this.roleName}">LINE</span>
                    <span class="ind-val" id="ind-mode-${this.roleName}">--</span>
                    <span class="ind-val" id="ind-int-${this.roleName}">--s</span>
                </div>

                <div style="margin-left:auto; font-family:monospace; font-size:1.5cqi; color:#aaa; flex-shrink:0;">
                    LAST: <span id="last-time-${this.roleName}">--:--:--</span>
                </div>
            </div>

            <div style="display:flex; align-items:center; gap:0.5cqi; margin-top:0.3cqi; font-family:monospace; font-size:1.8cqi; color:#aaa;">
                <span id="log-code-${this.roleName}" style="color:var(--accent-yellow);">[${this.conf.log_code || '---'}]</span>
                <span id="log-msg-${this.roleName}" style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                    ${this.conf.log_msg || 'Awaiting telemetry...'}
                </span>
            </div>
        `;
    }

    renderSettings() {
        const p = this.conf.val_params || {};
        const interval = p.val_interval !== undefined ? p.val_interval : 15;
        const recMode  = p.act_rec_mode !== undefined ? p.act_rec_mode : 0;
        const isRec    = p.act_rec === 1;
        const isDb     = p.act_db === 1;
        const isLine   = p.act_line === 1;

        return `
            <div style="font-size:2.2cqi; color:#888; display:flex; justify-content:space-between;">
                <span>HOLD INTERVAL (sec)</span>
                <span class="ui-val-s text-orange" id="val-int-disp-${this.roleName}">${interval}</span>
            </div>
            <input type="range" class="vst-slider vst-input" data-key="val_interval" min="5" max="60" value="${interval}" 
                   oninput="document.getElementById('val-int-disp-${this.roleName}').innerText=this.value">
            
            <div style="margin-top:1.5cqi; font-size:2cqi; color:#aaa;">RECORDING MODE</div>
            <select class="vst-input" data-key="act_rec_mode" style="width:100%; background:#111; color:#fff; border:1px solid #444; padding:0.5cqi; font-size:2cqi; margin-bottom:1.5cqi;">
                <option value="0" ${recMode == 0 ? 'selected' : ''}>SNAPSHOT</option>
                <option value="1" ${recMode == 1 ? 'selected' : ''}>VIDEO</option>
            </select>

            <div style="display:flex; justify-content:space-between; align-items:center; padding-top:1cqi; border-top:1px solid #333;">
                <label style="color:#ccc; font-size:2.2cqi; cursor:pointer;"><input type="checkbox" class="vst-input" data-key="act_rec" ${isRec ? 'checked' : ''}> REC</label>
                <label style="color:#ccc; font-size:2.2cqi; cursor:pointer;"><input type="checkbox" class="vst-input" data-key="act_db" ${isDb ? 'checked' : ''}> DB SAVE</label>
                <label style="color:#ccc; font-size:2.2cqi; cursor:pointer;"><input type="checkbox" class="vst-input" data-key="act_line" ${isLine ? 'checked' : ''}> LINE</label>
            </div>
        `;
    }

    // --- データ受信・描画更新ロジック ---
    updateFaceVisual(data) {
        // ステータス更新
        const statEl = document.getElementById(`stat-${this.roleName}`);
        if (statEl) {
            statEl.innerText = (data.val_status || 'IDLE').toUpperCase();
            statEl.style.color = (data.val_status === 'idle') ? 'var(--accent-green)' : 'var(--accent-orange)';
        }

        // LEDインジケーターの更新
        const setLed = (id, condition) => {
            const el = document.getElementById(id);
            if (el) el.className = `ind-led ${condition ? 'on' : ''}`;
        };
        setLed(`ind-rec-${this.roleName}`, data.act_rec === 1);
        setLed(`ind-db-${this.roleName}`, data.act_db === 1);
        setLed(`ind-line-${this.roleName}`, data.act_line === 1);

        // 値インジケーターの更新
        this.updateDOMText(`ind-mode-${this.roleName}`, data.act_rec_mode === 1 ? 'VIDEO' : 'SNAP');
        if (data.val_interval !== undefined) {
            this.updateDOMText(`ind-int-${this.roleName}`, `${data.val_interval}s`);
        }

        // 最終検知時間の更新
        if (data.env_last_detect) {
            const d = new Date(data.env_last_detect);
            this.updateDOMText(`last-time-${this.roleName}`, d.toLocaleTimeString('ja-JP', { hour12: false }));
        }

        // ログエリアの更新
        if (data.log_code) this.updateDOMText(`log-code-${this.roleName}`, `[${data.log_code}]`);
        if (data.log_msg) this.updateDOMText(`log-msg-${this.roleName}`, data.log_msg);
    }

    // MQTT update (ステータス変更や設定完了時)
    update(data) {
        // 設定値が送られてきた場合は同期
        if (data.cmd_status === 'completed' || data.log_ext) {
            const confData = data.log_ext || data;
            
            // UI部品の値を強制上書き
            const setInput = (key, val) => {
                const el = document.querySelector(`#settings-${this.roleName} .vst-input[data-key="${key}"]`);
                if (!el) return;
                if (el.type === 'checkbox') el.checked = (val === 1 || val === true);
                else el.value = val;
            };
            setInput('val_interval', confData.val_interval);
            setInput('act_rec_mode', confData.act_rec_mode);
            setInput('act_rec', confData.act_rec);
            setInput('act_db', confData.act_db);
            setInput('act_line', confData.act_line);
            
            // ベースクラスの正本データを再構築し、Dirty状態をリセット
            this.syncOriginalConfigFromDOM();
            
            if (data.cmd_status === 'completed') {
                this.updateLCD("Config sync complete.");
                this.ui.box.classList.remove('alert-header-yellow');
            }
        }

        this.updateFaceVisual(data);
    }

    // MQTT onEvent (検知イベント発火時)
    onEvent(data) {
        if (!this.val_enabled) return;

        if (data.event === 'motion_detected') {
            this.triggerAlert('RED', 'MOTION DETECTED');
            this.updateLCD(`MOTION DETECTED! Mode:${data.act_rec_mode===1?'VIDEO':'SNAP'}`, true);
            
            const statEl = document.getElementById(`stat-${this.roleName}`);
            if(statEl) statEl.style.color = "var(--accent-red)";
        }
        
        this.updateFaceVisual(data);
    }
}