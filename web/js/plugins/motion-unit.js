/**
 * WES 2026: MotionUnit (Inherits VstUnitBase)
 * V19 Rack Layout - Compact Settings & Fix LED Logic
 */
class MotionUnit extends VstUnitBase {
    constructor(conf, manager) {
        super(conf, manager);
    }

    // --- UI 構築 (HTML) ---
    renderFaceCenter() {
        const valName = this.conf.val_name || 'NO_NAME';
        const locName = this.conf.loc_name || 'UNKNOWN';
        const description = this.conf.vst_description || 'No Description';

        return `
            <div class="vst-plugin-motion" style="width:100%; display:flex; flex-direction:column; gap:2px;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div class="unit-id-row" style="font-weight:bold; color:#fff; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                        <span style="font-size:0.7rem; opacity:0.6;">${this.sysId} /</span> ${valName}
                    </div>
                    <div class="unit-desc-row" style="color:var(--accent-green); font-family:'Share Tech Mono'; text-align:right;">
                        ${description}
                    </div>
                </div>
                
                <div class="unit-loc-row" style="font-size:0.8rem; color:#888;">
                    ${locName}
                </div>

                <div style="display:flex; align-items:center; justify-content:space-between; margin-top:3px;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span id="stat-${this.roleName}" style="color:var(--accent-green); font-weight:bold; font-family:'Share Tech Mono'; min-width:45px;">IDLE</span>
                        <div class="led-container" style="display:flex; gap:4px;">
                            <span class="ind-led" id="ind-rec-${this.roleName}">REC</span>
                            <span class="ind-led" id="ind-db-${this.roleName}">DB</span>
                            <span class="ind-led" id="ind-line-${this.roleName}">LINE</span>
                        </div>
                    </div>
                    <div style="font-family:'Share Tech Mono'; font-size:0.8rem; background:rgba(0,0,0,0.3); padding:0 5px; border-radius:2px;">
                        <span id="ind-mode-${this.roleName}" style="color:var(--accent-orange);">--</span>
                        <span id="ind-int-${this.roleName}" style="margin-left:5px; color:#aaa;">--</span>
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

        // チェック判定の補助関数
        const isChecked = (val) => (val === 1 || val === true || val === '1') ? 'checked' : '';

        // スライダーを廃止し、省スペースなレイアウトに変更
        return `
            <div class="info-right motion-settings-compact">
                <div class="setting-row">
                    <span>HOLD INTERVAL (sec)</span>
                    <input type="number" class="vst-input num-input" data-key="val_interval" min="5" max="60" value="${interval}" 
                           onchange="this.closest('.vst-unit-box').vstInstance.syncAlert()">
                </div>
                
                <div class="setting-row" style="margin-bottom: 8px;">
                    <label class="chk-label">
                        <input type="checkbox" class="vst-input" data-key="val_alert_sync" id="sync-chk-${this.roleName}" 
                               ${alertSync ? 'checked' : ''} 
                               onchange="this.closest('.vst-unit-box').vstInstance.syncAlert()">
                        <span>HOLD INTERVALと同じにする</span>
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

    // 🌟 値変更時に連動するロジック
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

    // --- データ受信・描画更新ロジック ---
    updateFaceVisual(data) {
        // 設定値のベースは常に内部保持している this.conf.val_params とする
        const params = this.conf.val_params || {};

        // 判定用関数 (1, true, "1" など様々な型を吸収)
        const checkTrue = (val) => val === 1 || val === true || val === '1' || val === 'true';

        // ステータス更新
        const statEl = document.getElementById(`stat-${this.roleName}`);
        if (statEl) {
            const status = (data.val_status || 'idle').toLowerCase();
            statEl.innerText = status.toUpperCase();
            statEl.style.color = (status === 'idle') ? 'var(--accent-green)' : 'var(--accent-orange)';
        }

        // LEDインジケーターの更新（一時的なdataがあれば優先、無ければparamsベース）
        const setLed = (idSuffix, condition) => {
            const el = document.getElementById(`ind-${idSuffix}-${this.roleName}`);
            if (el) el.classList.toggle('on', condition);
        };

        const isRec  = (data.act_rec  !== undefined) ? checkTrue(data.act_rec)  : checkTrue(params.act_rec);
        const isDb   = (data.act_db   !== undefined) ? checkTrue(data.act_db)   : checkTrue(params.act_db);
        const isLine = (data.act_line !== undefined) ? checkTrue(data.act_line) : checkTrue(params.act_line);

        setLed('rec', isRec);
        setLed('db', isDb);
        setLed('line', isLine);

        // 値インジケーターの更新
        const recMode = (data.act_rec_mode !== undefined) ? data.act_rec_mode : params.act_rec_mode;
        this.updateDOMText(`ind-mode-${this.roleName}`, recMode == 1 ? 'VIDEO' : 'SNAP');

        const interval = (data.val_interval !== undefined) ? data.val_interval : params.val_interval;
        if (interval !== undefined) {
            this.updateDOMText(`ind-int-${this.roleName}`, `${interval}s`);
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

    // MQTT update (設定完了の受信時)
    update(data) {
        if (data.cmd_status === 'completed' || data.log_ext) {
            const confData = data.log_ext || data;
            const checkTrue = (val) => val === 1 || val === true || val === '1';
            
            // UI部品の値を強制上書き
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
            this.updateLCD(`MOTION DETECTED! Mode:${data.act_rec_mode==1?'VIDEO':'SNAP'}`, true);
            
            const statEl = document.getElementById(`stat-${this.roleName}`);
            if(statEl) {
                statEl.innerText = "DETECT";
                statEl.style.color = "var(--accent-red)";
            }

            // 🌟 動作中（点滅）アニメーションの開始 (ONになっているLEDだけを対象に)
            document.querySelectorAll(`#vst-box-${this.roleName} .ind-led.on`).forEach(el => el.classList.add('blink'));

            // 🌟 警告自動リセットのタイマー処理
            if (this.alertTimeout) clearTimeout(this.alertTimeout);

            // DOMから秒数を確実に取得
            const isSync = document.getElementById(`sync-chk-${this.roleName}`).checked;
            const holdInput = document.querySelector(`#settings-${this.roleName} [data-key="val_interval"]`);
            const alertInput = document.getElementById(`alert-num-${this.roleName}`);

            let intervalSec = 15; // フォールバック値
            if (isSync && holdInput) {
                intervalSec = parseInt(holdInput.value) || 15;
            } else if (!isSync && alertInput) {
                intervalSec = parseInt(alertInput.value) || 15;
            }

            // 指定時間経過後にアラート解除
            this.alertTimeout = setTimeout(() => {
                // 1Uアラート解除 (クラスを直接消す)
                this.ui.box.classList.remove('alert-header-red', 'alert-header-yellow', 'alert-border-red');
                
                // 点滅の解除
                document.querySelectorAll(`#vst-box-${this.roleName} .ind-led.blink`).forEach(el => el.classList.remove('blink'));
                
                // ステータスを元に戻す
                if(statEl) {
                    statEl.innerText = (this.conf.val_status || 'IDLE').toUpperCase();
                    statEl.style.color = "var(--accent-green)";
                }
            }, intervalSec * 1000);
        }
        
        this.updateFaceVisual(data);
    }
}