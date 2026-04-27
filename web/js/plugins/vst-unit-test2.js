/**
 * WES 2026: VstUnitTest2 (人感センサー 1U 3行レイアウト版)
 * Baseクラスを継承し、要件に合わせた完全なUIを提供します。
 */
class VstUnitTest2 extends VstUnitBase {
    constructor(conf, manager) {
        super(conf, manager);
    }

    /**
     * @override initUI()
     * Baseの骨格生成後に、右端へ死活チェックボタンを追加します。
     */
    initUI() {
        super.initUI(); // BaseによるDOMの生成

        const faceRight = this.ui.box.querySelector('.face-right');
        if (faceRight) {
            // 死活チェック（リロード）ボタンを生成
            const reloadBtn = document.createElement('button');
            reloadBtn.className = 'icon-btn ui-reload';
            reloadBtn.innerHTML = '↻';
            reloadBtn.title = '死活確認 (Status Request)';
            reloadBtn.onclick = () => this.pingNode();
            faceRight.appendChild(reloadBtn);
        }
    }

    /**
     * @override renderFaceCenter()
     * 1U部分の中央。要求通りの3行（ID/Name/Loc、LED、Status）を隙間なく配置します。
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
     * スライダーを廃止し、数値入力＋増減矢印(type=number標準)のレイアウト。
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

    /**
     * UI固有の連動メソッド：SYNCチェック時の数値入力制御
     */
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

    /**
     * 死活確認（リロード）ボタン押下時の処理
     */
    async pingNode() {
        this.updateLCD("Pinging node for latest status...");
        const btn = this.ui.box.querySelector('.ui-reload');
        if (btn) btn.style.transform = "rotate(360deg)"; // くるっと回す演出
        
        try {
            // 本来は api/send_cmd.php へ status_request をPOSTする
            console.log(`[API] Send ping to ${this.sysId}`);
            
            // デモ用の演出
            setTimeout(() => {
                this.updateLCD("Status Received. All systems nominal.");
                if (btn) btn.style.transform = "none";
            }, 1000);
        } catch (e) {
            this.updateLCD("Ping failed.", true);
            if (btn) btn.style.transform = "none";
        }
    }

    /**
     * @override
     * Hubから新しいデータを受信した際にFaceを更新する
     */
    updateFaceVisual(data) {
        // 設定値のベース
        const params = data.val_params || this.conf.val_params || {};
        const checkTrue = (val) => val === 1 || val === true || val === '1';

        // LEDの点灯反映
        const setLed = (idSuffix, condition) => {
            const el = document.getElementById(`led-${idSuffix}-${this.roleName}`);
            if (el) el.classList.toggle('on', condition);
        };
        setLed('rec', checkTrue(params.act_rec));
        setLed('db', checkTrue(params.act_db));
        setLed('line', checkTrue(params.act_line));

        // 3行目のステータス文字列更新
        const timeStr = data.updated_at || new Date().toLocaleTimeString('ja-JP', { hour12: false });
        const status = (data.val_status || 'IDLE').toUpperCase();
        const msg = data.log_msg || 'Ready';
        const code = data.log_code || 200;
        
        const r3 = document.getElementById(`r3-${this.roleName}`);
        if (r3) {
            r3.innerText = `[${timeStr}] ST:${status} | [${code}] ${msg}`;
        }
        
        // ログエリア(LCD)の更新
        if (msg) {
            const isError = code >= 400 || msg.includes('DETECTED');
            this.updateLCD(`[${code}] ${msg}`, isError);
            
            // 検知時は赤く点滅させる
            if (msg.includes('DETECTED')) {
                const idleLed = document.getElementById(`led-idle-${this.roleName}`);
                const recLed = document.getElementById(`led-rec-${this.roleName}`);
                if (idleLed) idleLed.classList.remove('on');
                if (recLed) recLed.classList.add('blink', 'red');
            }
        }
    }
}