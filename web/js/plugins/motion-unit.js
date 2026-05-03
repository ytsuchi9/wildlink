/**
 * WES 2026: MotionUnit (Inherits VstUnitBase)
 * ※GPIO(Pin4)等のPIRセンサー連携、動画/静止画記録を司るプラグイン
 * 🚨 エラー防止ガード：すでに読み込まれている場合は再定義しない
 */
if (typeof window.MotionUnit === 'undefined') {

    window.MotionUnit = class MotionUnit extends VstUnitBase {
        constructor(conf, manager) {
            super(conf, manager);
            this.actionTimers = { db: null, line: null };
        }

        renderFaceCenter() {
            const valName = this.conf.val_name || 'NO_NAME';
            const locName = this.conf.loc_name || 'UNKNOWN';
            const description = this.conf.vst_description || 'No Description';

            // 【課題5: r1-container が対象。CSSでアラートアニメーションがかかります】
            return `
                <div class="r1-container" id="r1-${this.roleName}">
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
            // 親クラスの更新（ステータス文字色や時刻など）を先に実行
            super.updateBaseVisual(data);

            const params = this.conf.val_params || {};
            const checkTrue = (val) => val === 1 || val === true || val === '1' || val === 'true';

            // 【課題6: LED設定ロジックの改善】
            // クラスを上書き(className=)せず、classListを使って基本構造を維持します。
            const setLed = (idSuffix, condition, colorClass) => {
                const el = document.getElementById(`ind-${idSuffix}-${this.roleName}`);
                if (el) {
                    // 基本クラスにリセット
                    el.className = 'ui-btn-led';
                    if (condition) {
                        el.classList.add(colorClass);
                    } else {
                        el.classList.add('led-off');
                    }
                }
            };

            // 設定状態に応じて基本色を配置
            setLed('rec', (data.act_rec !== undefined) ? checkTrue(data.act_rec) : checkTrue(params.act_rec), 'led-red');
            setLed('db', (data.act_db !== undefined) ? checkTrue(data.act_db) : checkTrue(params.act_db), 'led-green');
            setLed('line', (data.act_line !== undefined) ? checkTrue(data.act_line) : checkTrue(params.act_line), 'led-green');

            // 7セグ系の表示更新
            const recMode = (data.act_rec_mode !== undefined) ? data.act_rec_mode : params.act_rec_mode;
            this.updateDOMText(`ind-mode-${this.roleName}`, recMode == 1 ? 'VIDEO' : 'SNAP');

            const interval = (data.val_interval !== undefined) ? data.val_interval : params.val_interval;
            if (interval !== undefined) this.updateDOMText(`ind-int-${this.roleName}`, `${interval}s`);
            
            // 【課題5: 1U部1行目の反転アラート制御】
            const r1Container = this.ui.box.querySelector('.r1-container');
            if (r1Container) {
                r1Container.classList.remove('alert-row-red', 'alert-row-yellow', 'alert-row-green');
                const status = data.val_status ? data.val_status.toUpperCase() : '';
                
                if (status === 'ALERT' || status === 'DETECT' || status === 'ERROR') {
                    r1Container.classList.add('alert-row-red');
                } else if (status === 'WARNING') {
                    r1Container.classList.add('alert-row-yellow');
                }
                // IDLE等の正常時はクラス無し（背景透過）となる
            }

            // 状態に応じたエラーLED（赤・黄の上塗り）の更新呼び出し
            this.updateLEDs(data);
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
                
                // 【課題5連携】モーション検知時に即座に1行目を赤くする
                const r1Container = this.ui.box.querySelector('.r1-container');
                if(r1Container) r1Container.classList.add('alert-row-red');
                
                document.querySelectorAll(`#vst-box-${this.roleName} .ui-btn-led:not(.led-off)`).forEach(el => el.classList.add('led-blink'));

                if (this.alertTimeout) clearTimeout(this.alertTimeout);
                const isSync = document.getElementById(`sync-chk-${this.roleName}`).checked;
                const holdInput = document.querySelector(`#settings-${this.roleName} [data-key="val_interval"]`);
                const alertInput = document.getElementById(`alert-num-${this.roleName}`);
                let intervalSec = (isSync && holdInput) ? (parseInt(holdInput.value)||15) : ((parseInt(alertInput?.value))||15);

                this.alertTimeout = setTimeout(() => {
                    this.ui.box.classList.remove('alert-header-red', 'alert-header-yellow');
                    if(r1Container) r1Container.classList.remove('alert-row-red');
                    document.querySelectorAll(`#vst-box-${this.roleName} .led-blink`).forEach(el => el.classList.remove('led-blink'));
                    this.requestSync(true); 
                }, intervalSec * 1000);
            }
            this.updateFaceVisual(data);
        }

        // 🌟 HTTP/POSIX ハイブリッドエラーコード判定ロジック
        // 設定された基本LEDカラーの上から、エラー状況に応じて色を被せます
        updateLEDs(statusData) {
            const recLed = document.getElementById(`ind-rec-${this.roleName}`);
            if (!recLed) return;
            
            // 以前のエラーステータスをクリア
            recLed.classList.remove('led-error-red', 'led-error-yellow', 'led-blink-red');
            
            const code = statusData.log_code || 200;
            
            // 重大エラー (4xx, 5xx系)
            if (code >= 400 && code < 600) {
                recLed.classList.add('led-error-red');
            // 警告・注意 (3xx系, POSIXのEAGAIN等に相当する扱い)
            } else if (code >= 300 && code < 400) {
                recLed.classList.add('led-error-yellow');
            // 正常時：検知中(DETECT)の時のみREC点滅
            } else {
                if (statusData.val_status === 'DETECT' || statusData.val_status === 'detected') {
                    recLed.classList.add('led-blink-red');
                }
            }
        }

        // DBやLINEへの送信アクション時に関数を叩く
        triggerActionLED(targetId) {
            const led = document.getElementById(targetId);
            if (!led) return;
            led.classList.remove('led-blink-green-5'); 
            void led.offsetWidth; // 強制リフロー
            led.classList.add('led-blink-green-5');
        }
    }
}