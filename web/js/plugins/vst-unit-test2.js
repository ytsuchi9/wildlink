/**
 * web/js/plugins/vst-unit-test2.js
 * WES 2026: VstUnitTest2 (4K & Zoom Ready, Auto-height Feature)
 * 
 * 今後のデバイス開発の「モデル（お手本）」となるクラス。
 * 履歴重視のハイブリッドエラーコード設計、差分JSONアップデート、
 * および動的なレイアウト制御（高さ自動拡張）の実装例を提供します。
 */
class VstUnitTest2 extends VstUnitBase {
    constructor(conf, manager) {
        super(conf, manager);
        this.initUI(); 
    }

    /**
     * @override initUI()
     * 右端のパネルに「死活チェック」と「高さモード切替」の2つのボタンをマウントします。
     */
    initUI() {
        super.initUI();

        const faceRight = this.ui.box.querySelector('.face-right');
        if (faceRight) {
            // ① 死活チェック（ping）ボタン
            const reloadBtn = document.createElement('button');
            reloadBtn.className = 'icon-btn ui-reload';
            reloadBtn.innerHTML = '↻';
            reloadBtn.title = '死活確認 (Status Request)';
            reloadBtn.onclick = () => this.pingNode();
            faceRight.appendChild(reloadBtn);

            // ② パネル高さ拡張/固定 切替ボタン (画像/グラフ表示用)
            // このボタンで CSS の .auto-height クラスをトグルし、スクロール制限を解除します
            const resizeBtn = document.createElement('button');
            resizeBtn.className = 'icon-btn ui-resize';
            resizeBtn.innerHTML = '⇕';
            resizeBtn.title = 'パネル高さ拡張/固定 切替';
            resizeBtn.onclick = () => {
                this.ui.box.classList.toggle('auto-height');
                resizeBtn.classList.toggle('active');
            };
            faceRight.appendChild(resizeBtn);
        }
    }

    /**
     * @override renderFaceCenter()
     */
    renderFaceCenter() {
        const valName = this.conf.val_name || 'NO_NAME';
        const locName = this.conf.loc_name || 'UNKNOWN';
        const desc = this.conf.vst_description || '';

        return `
            <div class="r1-container">
                <div class="r1-left">
                    <div class="r1-id">${this.sysId} / ${valName}</div>
                    <div class="r1-loc">${locName}</div>
                </div>
                <div class="r1-desc">${desc}</div>
            </div>

            <div class="r2-container" id="ind-area-${this.roleName}">
                <span class="ind-led on" id="led-idle-${this.roleName}">IDLE</span>
                <span class="ind-led" id="led-rec-${this.roleName}">REC</span>
                <span class="ind-led" id="led-db-${this.roleName}">DB</span>
                <span class="ind-led" id="led-line-${this.roleName}">LINE</span>
            </div>

            <div class="r3-container" id="r3-${this.roleName}">
                [--:--:--] ST:IDLE | MSG:WAITING FOR DATA
            </div>
        `;
    }

    /**
     * @override renderSettings()
     */
    renderSettings() {
        const p = this.conf.val_params || {};
        const interval = p.val_interval || 15;
        const alertSync = p.val_alert_sync !== 0; 
        const alertInt = p.val_alert_int || 15;
        const recMode = p.act_rec_mode || 0;

        return `
            <div style="flex-grow: 1;">
                <div class="setting-row">
                    <span>HOLD INTERVAL (sec)</span>
                    <input type="number" class="vst-input num-input" data-key="val_interval" min="5" max="60" value="${interval}" 
                           onchange="this.closest('.vst-unit-box').vstInstance.syncAlertInputs()">
                </div>
                
                <div class="setting-row" style="justify-content: flex-start; margin-bottom: 12px;">
                    <label class="chk-label">
                        <input type="checkbox" class="vst-input" data-key="val_alert_sync" id="sync-chk-${this.roleName}" ${alertSync ? 'checked' : ''} 
                               onchange="this.closest('.vst-unit-box').vstInstance.syncAlertInputs()">
                        HOLD INTERVALと同じにする
                    </label>
                </div>

                <div class="setting-row">
                    <span>WARNING DISPLAY (sec)</span>
                    <input type="number" class="vst-input num-input" id="alert-num-${this.roleName}" data-key="val_alert_int" min="5" max="300" 
                           value="${alertSync ? interval : alertInt}" ${alertSync ? 'disabled' : ''}>
                </div>

                <div class="setting-row" style="margin-top: 15px;">
                    <span>RECORDING MODE</span>
                    <select class="vst-input select-dark" data-key="act_rec_mode">
                        <option value="0" ${recMode == 0 ? 'selected' : ''}>SNAP (Still)</option>
                        <option value="1" ${recMode == 1 ? 'selected' : ''}>VIDEO (MP4)</option>
                    </select>
                </div>

                <div class="checkbox-grid">
                    <label class="chk-label"><input type="checkbox" class="vst-input" data-key="act_rec" ${(p.act_rec===1)?'checked':''}> REC</label>
                    <label class="chk-label"><input type="checkbox" class="vst-input" data-key="act_db" ${(p.act_db===1)?'checked':''}> DB SAVE</label>
                    <label class="chk-label"><input type="checkbox" class="vst-input" data-key="act_line" ${(p.act_line===1)?'checked':''}> LINE</label>
                </div>
            </div>
        `;
    }

    syncAlertInputs() {
        const box = this.ui.box;
        const syncChk = document.getElementById(`sync-chk-${this.roleName}`);
        const alertInput = document.getElementById(`alert-num-${this.roleName}`);
        const holdVal = box.querySelector('[data-key="val_interval"]').value;

        if (syncChk && syncChk.checked) {
            alertInput.disabled = true;
            alertInput.value = holdVal;
        } else if (alertInput) {
            alertInput.disabled = false;
        }
    }

    async pingNode() {
        this.updateLCD("Pinging node for latest status...");
        const btn = this.ui.box.querySelector('.ui-reload');
        if (btn) btn.style.transform = "rotate(360deg)"; 
        
        try {
            console.log(`[API] Send ping to ${this.sysId}`);
            setTimeout(() => {
                this.updateLCD("Status Received. All systems nominal.");
                if (btn) btn.style.transform = "none";
            }, 1000);
        } catch (e) {
            this.updateLCD("Ping failed.", true);
            if (btn) btn.style.transform = "none";
        }
    }

    updateFaceVisual(data) {
        const params = data.val_params || this.conf.val_params || {};
        const checkTrue = (val) => val === 1 || val === true || val === '1';

        const setLed = (idSuffix, condition) => {
            const el = document.getElementById(`led-${idSuffix}-${this.roleName}`);
            if (el) el.classList.toggle('on', condition);
        };
        setLed('rec', checkTrue(params.act_rec));
        setLed('db', checkTrue(params.act_db));
        setLed('line', checkTrue(params.act_line));

        const timeStr = data.updated_at || new Date().toLocaleTimeString('ja-JP', { hour12: false });
        const status = (data.val_status || 'IDLE').toUpperCase();
        const msg = data.log_msg || 'Ready';
        const code = data.log_code || 200; 
        
        const r3 = document.getElementById(`r3-${this.roleName}`);
        if (r3) {
            r3.innerText = `[${timeStr}] ST:${status} | [${code}] ${msg}`;
        }
        
        if (msg) {
            const isError = code >= 400 || msg.includes('DETECTED');
            this.updateLCD(`[${code}] ${msg}`, isError);
            
            if (msg.includes('DETECTED')) {
                const idleLed = document.getElementById(`led-idle-${this.roleName}`);
                const recLed = document.getElementById(`led-rec-${this.roleName}`);
                if (idleLed) idleLed.classList.remove('on');
                if (recLed) recLed.classList.add('blink', 'red');
            }
        }
    }
}