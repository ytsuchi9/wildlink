/**
 * WES 2026: MotionUnit (Inherits VstUnitBase)
 */
class MotionUnit extends VstUnitBase {
    constructor(conf, manager) {
        super(conf, manager);
    }

    // 🌟 完璧に調整済みのCSSクラス(r1-container, ui-part-group等)を再利用
    renderFaceCenter() {
        const valName = this.conf.val_name || 'NO_NAME';
        const locName = this.conf.loc_name || 'UNKNOWN';
        const description = this.conf.vst_description || 'No Description';

        return `
            <div class="r1-container">
                <div class="r1-left">
                    <div class="r1-id">${this.sysId} / ${valName}</div>
                    <div class="r1-loc">${locName}</div>
                </div>
                <div class="r1-desc">${description}</div>
            </div>

            <div class="r2-container" id="ind-area-${this.roleName}">
                <div class="ui-part-group">
                    <div class="ui-btn-led led-off" id="ind-rec-${this.roleName}">REC</div>
                </div>
                <div class="ui-part-group">
                    <div class="ui-btn-led led-off" id="ind-db-${this.roleName}">DB</div>
                </div>
                <div class="ui-part-group">
                    <div class="ui-btn-led led-off" id="ind-line-${this.roleName}">LINE</div>
                </div>
                
                <div style="margin-left: auto; display:flex; gap: 10px; align-items:flex-end;">
                    <div class="ui-part-group">
                        <div class="ui-7seg" id="ind-mode-${this.roleName}">--</div>
                        <div class="ui-part-label">MODE</div>
                    </div>
                    <div class="ui-part-group">
                        <div class="ui-7seg" id="ind-int-${this.roleName}">--s</div>
                        <div class="ui-part-label">INTVL</div>
                    </div>
                </div>
            </div>
        `;
    }

    renderSettings() {
        const p = this.conf.val_params || {};
        const interval = p.val_interval || 15;
        const alertSync = p.val_alert_sync !== 0; 
        const alertInt = p.val_alert_int || 15;
        const recMode = p.act_rec_mode || 0;
        const isChecked = (val) => (val === 1 || val === true || val === '1') ? 'checked' : '';

        return `
            <div class="info-right motion-settings-compact" style="padding-top:0;">
                <div class="setting-row">
                    <span>HOLD INTERVAL (sec)</span>
                    <input type="number" class="vst-input num-input" data-key="val_interval" min="5" max="60" value="${interval}" 
                           onchange="this.closest('.vst-unit-box').vstInstance.syncAlert()">
                </div>
                <div class="setting-row" style="margin-bottom: 8px;">
                    <label class="chk-label">
                        <input type="checkbox" class="vst-input" data-key="val_alert_sync" id="sync-chk-${this.roleName}" 
                               ${alertSync ? 'checked' : ''} onchange="this.closest('.vst-unit-box').vstInstance.syncAlert()">
                        HOLD INTERVALと同じにする
                    </label>
                </div>
                <div class="setting-row">
                    <span>WARNING DISPLAY (sec)</span>
                    <input type="number" class="vst-input num-input" id="alert-num-${this.roleName}" data-key="val_alert_int" min="5" max="300" 
                           value="${alertSync ? interval : alertInt}" ${alertSync ? 'disabled' : ''}>
                </div>
                <hr style="border: 0; border-top: 1px solid #333; margin: 10px 0 8px 0;">
                <div class="setting-row">
                    <span>RECORDING MODE</span>
                    <select class="vst-input select-dark" data-key="act_rec_mode" style="width: 120px;">
                        <option value="0" ${recMode == 0 ? 'selected' : ''}>SNAP (Still)</option>
                        <option value="1" ${recMode == 1 ? 'selected' : ''}>VIDEO (MP4)</option>
                    </select>
                </div>
                <div class="checkbox-grid">
                    <label class="chk-label"><input type="checkbox" class="vst-input" data-key="act_rec" ${isChecked(p.act_rec)}> REC</label>
                    <label class="chk-label"><input type="checkbox" class="vst-input" data-key="act_db" ${isChecked(p.act_db)}> DB SAVE</label>
                    <label class="chk-label"><input type="checkbox" class="vst-input" data-key="act_line" ${isChecked(p.act_line)}> LINE</label>
                </div>
            </div>
        `;
    }

    syncAlert() {
        const box = this.ui.box;
        const syncChk = document.getElementById(`sync-chk-${this.roleName}`);
        const numInput = document.getElementById(`alert-num-${this.roleName}`);
        const holdVal = box.querySelector('[data-key="val_interval"]').value;
        if (syncChk && syncChk.checked) {
            numInput.disabled = true;
            numInput.value = holdVal;
        } else if (numInput) {
            numInput.disabled = false;
        }
    }

    updateFaceVisual(data) {
        super.updateBaseVisual(data); // 1U最下行の更新

        const params = this.conf.val_params || {};
        const checkTrue = (val) => val === 1 || val === true || val === '1' || val === 'true';

        // 🌟 新しいLEDクラスの切り替え処理 (赤と緑を使い分け)
        const setLed = (idSuffix, condition, colorClass) => {
            const el = document.getElementById(`ind-${idSuffix}-${this.roleName}`);
            if (el) el.className = `ui-btn-led ${condition ? colorClass : 'led-off'}`;
        };

        setLed('rec', (data.act_rec !== undefined) ? checkTrue(data.act_rec) : checkTrue(params.act_rec), 'led-red');
        setLed('db', (data.act_db !== undefined) ? checkTrue(data.act_db) : checkTrue(params.act_db), 'led-green');
        setLed('line', (data.act_line !== undefined) ? checkTrue(data.act_line) : checkTrue(params.act_line), 'led-green');

        const recMode = (data.act_rec_mode !== undefined) ? data.act_rec_mode : params.act_rec_mode;
        this.updateDOMText(`ind-mode-${this.roleName}`, recMode == 1 ? 'VIDEO' : 'SNAP');

        const interval = (data.val_interval !== undefined) ? data.val_interval : params.val_interval;
        if (interval !== undefined) this.updateDOMText(`ind-int-${this.roleName}`, `${interval}s`);
    }

    update(data) {
        if (data.cmd_status === 'completed' || data.log_ext) {
            const confData = data.log_ext || data;
            const checkTrue = (val) => val === 1 || val === true || val === '1';
            
            const setInput = (key, val) => {
                const el = document.querySelector(`#settings-${this.roleName} .vst-input[data-key="${key}"]`);
                if (!el) return;
                if (el.type === 'checkbox') el.checked = checkTrue(val);
                else el.value = val;
            };
            
            setInput('val_interval', confData.val_interval);
            setInput('act_rec_mode', confData.act_rec_mode);
            setInput('act_rec', confData.act_rec);
            setInput('act_db', confData.act_db);
            setInput('act_line', confData.act_line);
            
            this.syncOriginalConfigFromDOM();
            
            if (data.cmd_status === 'completed') {
                this.updateLCD("Config synced.", data.log_ext);
                this.ui.box.classList.remove('alert-header-yellow');
            }
        }
        this.updateFaceVisual(data);
    }

    onEvent(data) {
        if (!this.val_enabled) return;

        if (data.event === 'motion_detected') {
            this.triggerAlert('RED', 'MOTION DETECTED');
            this.updateLCD(`MOTION DETECTED! Mode:${data.act_rec_mode==1?'VIDEO':'SNAP'}`, data.log_ext, true);
            
            // 点灯中のLEDを点滅させる
            document.querySelectorAll(`#vst-box-${this.roleName} .ui-btn-led:not(.led-off)`).forEach(el => el.classList.add('led-blink'));

            if (this.alertTimeout) clearTimeout(this.alertTimeout);
            const isSync = document.getElementById(`sync-chk-${this.roleName}`).checked;
            const holdInput = document.querySelector(`#settings-${this.roleName} [data-key="val_interval"]`);
            const alertInput = document.getElementById(`alert-num-${this.roleName}`);
            let intervalSec = (isSync && holdInput) ? (parseInt(holdInput.value)||15) : ((parseInt(alertInput?.value))||15);

            this.alertTimeout = setTimeout(() => {
                this.ui.box.classList.remove('alert-header-red', 'alert-header-yellow');
                document.querySelectorAll(`#vst-box-${this.roleName} .led-blink`).forEach(el => el.classList.remove('led-blink'));
                this.requestSync(true); 
            }, intervalSec * 1000);
        }
        this.updateFaceVisual(data);
    }

    updateLEDs(statusData) {
        const recLed = this.ui.box.querySelector('.led-rec');
        
        // 基本状態 (有効なら緑)
        if (this.conf.val_enabled) this.ui.box.querySelector('.led-main').classList.add('led-valid');

        // エラー判定 (HTTP/POSIXハイブリッドコード)
        const code = statusData.log_code || 200;
        if (code >= 400 && code < 600) {
            // 重大エラー (4xx, 5xx系)
            recLed.className = 'led-indicator led-error-red';
        } else if (code >= 300 && code < 400) {
            // 警告・注意 (3xx系, POSIXのEAGAIN等に相当する扱い)
            recLed.className = 'led-indicator led-error-yellow';
        } else {
            // 正常時：REC点滅ロジック
            if (statusData.val_status === 'detected') {
                recLed.classList.add('led-blink-red');
            } else {
                recLed.classList.remove('led-blink-red');
            }
        }
    }

    // DBやLINEへの送信アクション時に関数を叩く
    triggerActionLED(targetClass) {
        const led = this.ui.box.querySelector(targetClass);
        led.classList.remove('led-blink-green-5'); // 一旦リセット
        void led.offsetWidth; // 強制リフロー（アニメーション再起動の魔法）
        led.classList.add('led-blink-green-5');
    }

}