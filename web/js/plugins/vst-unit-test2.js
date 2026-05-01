/**
 * web/js/plugins/vst-unit-test2.js
 * WES 2026: VstUnitTest2 (UI Components & Logic Model)
 * 
 * 今後のデバイス開発の「お手本」となるクラスです。
 * 7セグメント、レベルメーター、押しボタンLEDの動的制御、
 * および1U行目のアラートアニメーション(緑ACK等)の実装例を提供します。
 */
class VstUnitTest2 extends VstUnitBase {
    constructor(conf, manager) {
        super(conf, manager);
        this.initUI(); 
        this.startMockSensors(); // テスト用の動的メーター更新を開始
    }

    initUI() {
        super.initUI();

        const faceRight = this.ui.box.querySelector('.face-right');
        if (faceRight) {
            // 死活チェック（ping）ボタン。押すと1行目がACK(緑)で光るテストを兼ねる
            const reloadBtn = document.createElement('button');
            reloadBtn.className = 'icon-btn ui-reload';
            reloadBtn.innerHTML = '↻';
            reloadBtn.title = '死活確認 (Status Request)';
            reloadBtn.onclick = () => {
                this.pingNode();
                this.triggerRowAlert('green'); // ACKの緑点滅
            };
            faceRight.appendChild(reloadBtn);

            // パネル高さ切替ボタン
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
     * ここで新しいUIモジュール枠(.ui-part-group)を使ったレイアウトを生成します。
     */
    renderFaceCenter() {
        const valName = this.conf.val_name || 'NO_NAME';
        const locName = this.conf.loc_name || 'UNKNOWN';
        const desc = this.conf.vst_description || '';

        return `
            <div class="r1-container" id="r1-${this.roleName}">
                <div class="r1-left">
                    <div class="r1-id">${this.sysId} / ${valName}</div>
                    <div class="r1-loc">${locName}</div>
                </div>
                <div class="r1-desc">${desc}</div>
            </div>

            <div class="r2-container" id="ind-area-${this.roleName}">
                
                <!-- 1. 状態表示LED -->
                <div class="ui-part-group">
                    <div class="ui-btn-led led-off" id="led-rec-${this.roleName}">REC</div>
                    <div class="ui-part-label">STATUS</div>
                </div>

                <!-- 2. 操作可能押しボタン (クリックで状態が変わる想定) -->
                <div class="ui-part-group">
                    <button class="ui-btn-led led-off" id="btn-stream-${this.roleName}" onclick="this.closest('.vst-unit-box').vstInstance.toggleStream()">STRM</button>
                    <div class="ui-part-label">ACTION</div>
                </div>

                <!-- 3. 7セグメント風数値表示 -->
                <div class="ui-part-group">
                    <div class="ui-7seg" id="val-temp-${this.roleName}">--.-</div>
                    <div class="ui-part-label">TEMP(C)</div>
                </div>

                <!-- 4. レベルメーター -->
                <div class="ui-part-group">
                    <div class="ui-meter-box">
                        <div class="ui-meter-bar" id="meter-cpu-${this.roleName}" style="width: 0%;"></div>
                    </div>
                    <div class="ui-part-label">CPU LOAD</div>
                </div>

            </div>

            <div class="r3-container" id="r3-${this.roleName}">
                [--:--:--] ST:IDLE | MSG:WAITING FOR DATA
            </div>
        `;
    }

    /**
     * 1行目(.r1-container)のアラート状態を変更します。
     * @param {string} color - 'red', 'yellow', 'green'(ACK用), 'none'(解除)
     */
    triggerRowAlert(color) {
        const row1 = document.getElementById(`r1-${this.roleName}`);
        if (!row1) return;
        
        row1.classList.remove('alert-row-red', 'alert-row-yellow', 'alert-row-green');
        if (color && color !== 'none') {
            row1.classList.add(`alert-row-${color}`);
        }
    }

    /**
     * STRMボタンが押された時のトグル処理（機器へのコマンド送信をシミュレート）
     */
    toggleStream() {
        const btn = document.getElementById(`btn-stream-${this.roleName}`);
        if (!btn) return;

        if (btn.classList.contains('led-off')) {
            // 起動コマンド送信状態 (緑点灯)
            btn.classList.replace('led-off', 'led-green');
            this.updateLCD("Streaming process started...");
        } else {
            // 停止コマンド送信状態 (消灯へ)
            btn.classList.remove('led-green', 'led-red', 'led-blink');
            btn.classList.add('led-off');
            this.updateLCD("Streaming stopped.");
        }
    }

    /**
     * [テスト用] レベルメーターと7セグを動的に更新するモックロジック
     */
    startMockSensors() {
        setInterval(() => {
            const cpuMeter = document.getElementById(`meter-cpu-${this.roleName}`);
            const tempDisp = document.getElementById(`val-temp-${this.roleName}`);
            
            if (cpuMeter) {
                const load = Math.floor(Math.random() * 100);
                cpuMeter.style.width = `${load}%`;
            }
            if (tempDisp) {
                const temp = (35 + Math.random() * 15).toFixed(1);
                tempDisp.textContent = temp;
            }
        }, 2000); // 2秒ごとに変動
    }

    // ----------------------------------------------------
    // 既存機能・基盤ロジック
    // ----------------------------------------------------
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
                setTimeout(() => this.triggerRowAlert('none'), 1500); // 1.5秒後にACK緑を消す
            }, 1000);
        } catch (e) {
            this.updateLCD("Ping failed.", true);
            if (btn) btn.style.transform = "none";
        }
    }

    updateFaceVisual(data) {
        const params = data.val_params || this.conf.val_params || {};
        const checkTrue = (val) => val === 1 || val === true || val === '1';

        // REC LEDの制御 (点滅/点灯/消灯をクラスで切り替え)
        const recLed = document.getElementById(`led-rec-${this.roleName}`);
        if (recLed) {
            recLed.className = 'ui-btn-led'; // リセット
            if (checkTrue(params.act_rec)) {
                recLed.classList.add('led-red', 'led-blink');
            } else {
                recLed.classList.add('led-off');
            }
        }

        // 時刻の生成。タイムゾーンをJST（日本標準時）に強制し、確実に現地時間で表示
        const timeOpts = { timeZone: 'Asia/Tokyo', hour12: false };
        const timeStr = data.updated_at || new Date().toLocaleTimeString('ja-JP', timeOpts);
        
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
                // MOTION DETECTED などのアラート発生時、1行目を赤点滅にする
                this.triggerRowAlert('red');
            }
        }
    }
}