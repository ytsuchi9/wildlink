/**
 * WES 2026: VstUnitBase (Rack System v17 Core)
 * ※UIの基本骨格と、サーバーとの通信（Apply/Sync）を担う基底クラス
 */
class VstUnitBase {
    constructor(conf, manager) {
        this.manager = manager;
        this.conf = Object.assign({
            vst_description: 'Unit', vst_role_name: 'vst_0', sys_id: 'sys_0', loc_name: 'UNKNOWN',
            val_enabled: 1, val_status: 'IDLE', log_msg: 'Ready.', log_code: 200,
            poll_interval: 60000 
        }, conf);
        
        this.roleName = this.conf.vst_role_name;
        this.sysId = this.conf.sys_id;
        this.val_enabled = (parseInt(this.conf.val_enabled) === 1);
        
        this.originalConfig = {};
        this.isExpanded = false;
        this.isKeep = false;
        this.isDirty = false;
        this.ui = {};
        this.pollTimer = null;
    }

    initUI() {
        const container = document.getElementById(`content-${this.roleName}`);
        if (!container) return;

        const pluginWrapper = document.getElementById(`plugin-${this.roleName}`);
        if (pluginWrapper) {
            pluginWrapper.className = ''; 
            const header = pluginWrapper.querySelector('.plugin-header');
            if (header) header.style.display = 'none';
        }

        container.innerHTML = `
            <div class="vst-unit-box" id="vst-box-${this.roleName}">
                <div class="vst-unit-face">
                    <div class="face-left">
                        <label class="power-switch-v">
                            <input type="checkbox" class="ui-sw vst-input" data-key="val_enabled" ${this.val_enabled ? 'checked' : ''}>
                            <span class="slider"></span>
                        </label>
                        <!-- 【課題3: 左側のボタンを APPLY に変更し、変更検知(Dirty)と連動させる】 -->
                        <button class="btn-vst apply-btn-mini ui-apply" title="Apply Changes">APPLY</button>
                    </div>
                    
                    <div class="face-center" id="face-center-${this.roleName}">
                        ${this.renderFaceCenter()}
                        
                        <div class="r3-container" style="display:flex; justify-content:space-between; border-top:1px dashed #333; padding-top:4px; margin-top:auto;">
                            <div style="display:flex; gap:8px;">
                                <!-- ユーザー指定: JST(日本時間)での表示を徹底 -->
                                <span id="base-time-${this.roleName}" style="font-family:'Share Tech Mono';">--:--:--</span>
                                <span id="base-status-${this.roleName}" style="font-weight:bold;">IDLE</span>
                                <span id="base-code-${this.roleName}" style="color:var(--accent-orange);">[---]</span>
                            </div>
                            <span id="base-msg-${this.roleName}" style="text-align:right; overflow:hidden; text-overflow:ellipsis;">Waiting...</span>
                        </div>
                    </div>

                    <div class="face-right">
                        <button class="btn-vst ui-exp" title="設定展開">▼</button>
                        <button class="btn-vst ui-keep" title="固定">＄</button>
                        <button class="btn-vst ui-scroll-mode" title="スクロール・段階的拡張切替">⇅</button>
                        <button class="btn-vst ui-ping" title="死活確認">↻</button>
                    </div>
                </div>
                <div class="unit-body">
                    <div class="test-lcd ui-lcd" id="lcd-${this.roleName}">
                        <span style="color:#555;">[${new Date().toLocaleTimeString('ja-JP', { timeZone: 'Asia/Tokyo' })}]</span> SYSTEM READY.
                    </div>
                    <div class="settings-area" id="settings-${this.roleName}">
                        ${this.renderSettings()}
                        <!-- 【課題2: 設定項目とボタンの重なり防止】 CSSの settings-bottom-controls で最下部に押しやる -->
                        <div class="settings-bottom-controls">
                            <button class="btn-vst action-btn ui-reset">RESET</button>
                            <button class="btn-vst action-btn ui-apply">APPLY</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // UI要素のマッピング
        this.ui = {
            box: document.getElementById(`vst-box-${this.roleName}`),
            sw: container.querySelector('.ui-sw'),
            // 左側のミニボタンと、アコーディオン内のメインボタンの両方を一括取得
            // applies: container.querySelectorAll('.ui-apply'), 
            sync: container.querySelector('.ui-sync'),
            applies: container.querySelectorAll('.ui-apply, .power-apply-btn'), // 両方の適用ボタン
            reset: container.querySelector('.ui-reset'),
            exp: container.querySelector('.ui-exp'),
            keep: container.querySelector('.ui-keep'),
            scroll: container.querySelector('.ui-scroll-mode'),
            ping: container.querySelector('.ui-ping'),
            lcd: document.getElementById(`lcd-${this.roleName}`)
        };

        // HTML内の onchange 属性等からアクセスできるようにする
        this.ui.box.vstInstance = this;

        this.bindEvents();
        setTimeout(() => this.syncOriginalConfigFromDOM(), 300);
        this.updateBaseVisual(this.conf);
    }

    renderFaceCenter() { return ``; }
    renderSettings() { return ``; }

    bindEvents() {
        this.ui.exp.onclick = () => this.toggleAccordion();
        this.ui.keep.onclick = () => this.toggleKeep();

        if (this.ui.scroll) {
            this.ui.scroll.onclick = () => {
                // 【課題1: スクロール可否ボタンの対象変更】
                // LCD画面単体ではなく、親要素(box)に 'auto-height' クラスを付与し、CSS側で高さを拡張させる
                const isAutoHeight = this.ui.box.classList.toggle('auto-height');
                this.ui.scroll.classList.toggle('active', isAutoHeight);
            };
        }

        if (this.ui.ping) this.ui.ping.onclick = () => this.requestSync(false);
        this.ui.reset.onclick = () => this.resetSettings();
        
        // 【課題3: APPLYボタン複数対応】querySelectorAllで取得した全てのAPPLYボタンにイベントを紐付け
        this.ui.applies.forEach(btn => btn.onclick = () => this.applySettings());

        const inputs = document.querySelectorAll(`#vst-box-${this.roleName} .vst-input`);
        inputs.forEach(input => {
            input.addEventListener('change', () => this.checkDirtyState());
            input.addEventListener('input', () => this.checkDirtyState());
        });
    }

    updateBaseVisual(data) {
        // 日本時間 (JST) での時刻表示
        if (data.updated_at || data.env_last_detect) {
            const d = new Date(data.updated_at || data.env_last_detect);
            this.updateDOMText(`base-time-${this.roleName}`, d.toLocaleTimeString('ja-JP', { hour12: false, timeZone: 'Asia/Tokyo' }));
        }

        if (data.val_status) {
            const statEl = document.getElementById(`base-status-${this.roleName}`);
            if (statEl) {
                const status = data.val_status.toUpperCase();
                statEl.innerText = status;
                statEl.style.color = (status === 'ALERT' || status === 'DETECT' || status === 'ERROR') ? 'var(--accent-red)' : 'var(--accent-green)';
            }
        }
        if (data.log_code) this.updateDOMText(`base-code-${this.roleName}`, `[${data.log_code}]`);
        if (data.log_msg) this.updateDOMText(`base-msg-${this.roleName}`, data.log_msg);
    }

    updateLCD(msg, logExt = null, isRed = false) {
        if (!this.ui.lcd) return;
        const t = new Date().toLocaleTimeString('ja-JP', { hour12: false, timeZone: 'Asia/Tokyo' });
        const color = isRed ? 'var(--accent-red)' : 'var(--accent-green)';
        let html = `<br><span style="color:#555;">[${t}]</span> <span style="color:${color};">${msg}</span>`;
        
        if (logExt && typeof logExt === 'object') {
            html += `<div style="margin-left: 15px; font-size: 0.85rem; color: #aaa; border-left: 1px dashed #444; padding-left: 8px; margin-top: 2px;">`;
            for (const [key, val] of Object.entries(logExt)) {
                const displayVal = typeof val === 'object' ? JSON.stringify(val) : val;
                html += `<div><span style="color:var(--accent-orange);">${key}:</span> ${displayVal}</div>`;
            }
            html += `</div>`;
        }
        this.ui.lcd.innerHTML += html;
        this.ui.lcd.scrollTop = this.ui.lcd.scrollHeight;
    }

    startPolling() {
        if (this.pollTimer) clearInterval(this.pollTimer);
        this.pollTimer = setInterval(() => { this.requestSync(true); }, this.conf.poll_interval);
    }

    async requestSync(isSilent = false) {
        if (!isSilent) this.triggerAlert('YELLOW', 'SYNC...');
        try {
            const formData = new URLSearchParams();
            formData.append('sys_id', this.manager.nodeId);
            formData.append('cmd_type', 'ping');
            formData.append('cmd_json', JSON.stringify({ role: this.roleName }));
            await fetch('api/send_cmd.php', { method: 'POST', body: formData });
            if (!isSilent) this.updateLCD("Sync request sent.");
        } catch (e) {
            this.updateLCD("Sync request FAILED.", null, true);
        }
    }

    async applySettings() {
        if (!this.isDirty) return;
        this.triggerAlert('YELLOW', 'APPLYING...');
        
        // 全てのAPPLYボタンを無効化し、成功状態の色に変更
        this.ui.applies.forEach(btn => { 
            btn.classList.remove('dirty'); 
            btn.classList.add('success'); 
            btn.disabled = true; 
        });

        try {
            const formData = new URLSearchParams();
            formData.append('sys_id', this.manager.nodeId);
            formData.append('cmd_type', 'update_config');
            const payload = { role: this.roleName };
            document.querySelectorAll(`#vst-box-${this.roleName} .vst-input`).forEach(input => {
                const key = input.getAttribute('data-key');
                if (key) payload[key] = input.type === 'checkbox' ? (input.checked ? 1 : 0) : parseFloat(input.value);
            });
            // DB設計コンセプトに基づく、差分パッチ(cmd_json)の発行
            formData.append('cmd_json', JSON.stringify(payload));
            await fetch('api/send_cmd.php', { method: 'POST', body: formData });
            
            // 適用成功時に現在の状態を正とする
            this.syncOriginalConfigFromDOM();
            
        } catch (e) {
            this.updateLCD("Apply FAILED.", null, true);
        } finally {
            this.ui.applies.forEach(btn => { 
                btn.classList.remove('success'); 
                btn.disabled = false; 
            });
        }
    }

    syncOriginalConfigFromDOM() {
        this.originalConfig = {};
        document.querySelectorAll(`#vst-box-${this.roleName} .vst-input`).forEach(input => {
            const key = input.getAttribute('data-key');
            if (key) this.originalConfig[key] = input.type === 'checkbox' ? (input.checked ? "1" : "0") : String(input.value).trim();
        });
        this.checkDirtyState();
    }

    checkDirtyState() {
        this.isDirty = false;
        document.querySelectorAll(`#vst-box-${this.roleName} .vst-input`).forEach(input => {
            const key = input.getAttribute('data-key');
            if (!key) return;
            const current = input.type === 'checkbox' ? (input.checked ? "1" : "0") : String(input.value).trim();
            if (current !== this.originalConfig[key]) this.isDirty = true;
        });
        
        if (this.isDirty) {
            // 変更があれば全てのAPPLYボタンを黄色く光らせる（dirtyクラス）
            this.ui.applies.forEach(btn => btn.classList.add('dirty'));
            this.ui.reset.classList.add('active');
        } else {
            this.ui.applies.forEach(btn => btn.classList.remove('dirty'));
            this.ui.reset.classList.remove('active');
        }
    }

    resetSettings() {
        if (!this.isDirty || !confirm("変更を破棄しますか？")) return;
        document.querySelectorAll(`#vst-box-${this.roleName} .vst-input`).forEach(input => {
            const key = input.getAttribute('data-key');
            if (!key || this.originalConfig[key] === undefined) return;
            if (input.type === 'checkbox') input.checked = (this.originalConfig[key] === "1");
            else input.value = this.originalConfig[key];
        });
        this.checkDirtyState();
    }

    toggleAccordion() {
        if (this.isKeep && this.isExpanded) return;
        this.isExpanded = !this.isExpanded;
        this.ui.box.classList.toggle('expanded', this.isExpanded);
        this.ui.exp.innerText = this.isExpanded ? '▲' : '⛶';
        this.ui.exp.classList.toggle('active', this.isExpanded);
    }
    
    toggleKeep() {
        this.isKeep = !this.isKeep;
        this.ui.keep.classList.toggle('active', this.isKeep);
        if (this.isKeep && !this.isExpanded) this.toggleAccordion();
    }
    
    updateDOMText(id, text) { const el = document.getElementById(id); if (el) el.innerText = text; }
    
    triggerAlert(level, msg) {
        const lvl = level.toUpperCase();
        this.ui.box.classList.remove('alert-header-red', 'alert-header-yellow');
        if (lvl === 'RED') {
            this.ui.box.classList.add('alert-header-red');
            if (!this.isExpanded) this.toggleAccordion();
        } else if (lvl === 'YELLOW') {
            this.ui.box.classList.add('alert-header-yellow');
        }
    }
}