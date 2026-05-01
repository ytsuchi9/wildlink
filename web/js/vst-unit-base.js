/**
 * WES 2026: VstUnitBase (Rack System v17 Core)
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
                        <button class="btn-vst apply-btn-mini ui-sync" title="Sync / Ping">SYNC</button>
                    </div>
                    
                    <div class="face-center" id="face-center-${this.roleName}">
                        ${this.renderFaceCenter()}
                        
                        <div class="r3-container" style="display:flex; justify-content:space-between; border-top:1px dashed #333; padding-top:4px; margin-top:auto;">
                            <div style="display:flex; gap:8px;">
                                <span id="base-time-${this.roleName}" style="font-family:'Share Tech Mono';">--:--:--</span>
                                <span id="base-status-${this.roleName}" style="font-weight:bold;">IDLE</span>
                                <span id="base-code-${this.roleName}" style="color:var(--accent-orange);">[---]</span>
                            </div>
                            <span id="base-msg-${this.roleName}" style="text-align:right; overflow:hidden; text-overflow:ellipsis;">Waiting...</span>
                        </div>
                    </div>

                    <div class="face-right" style="display: flex; flex-direction: column; gap: 8px; justify-content: flex-start; padding-top: 10px;">
                        <button class="btn-vst ui-exp" title="設定展開">▼</button>
                        <button class="btn-vst ui-keep" title="固定">＄</button>
                        <button class="btn-vst ui-scroll-mode" title="スクロール切替">⇅</button>
                        <button class="btn-vst ui-ping" title="死活確認">↻</button>
                    </div>
                </div>
                <div class="unit-body">
                    <div class="test-lcd ui-lcd" id="lcd-${this.roleName}">
                        <span style="color:#555;">[${new Date().toLocaleTimeString('ja-JP')}]</span> SYSTEM READY.
                    </div>
                    <div class="settings-area" id="settings-${this.roleName}">
                        ${this.renderSettings()}
                        <div style="display:flex;gap:0.5cqi;margin-top:auto;">
                            <button class="btn-vst action-btn ui-reset">RESET</button>
                            <button class="btn-vst action-btn ui-apply">APPLY</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // initUIメソッド内の uiオブジェクト定義部分を更新
        this.ui = {
            box: document.getElementById(`vst-box-${this.roleName}`),
            sw: container.querySelector('.ui-sw'),
            sync: container.querySelector('.ui-sync'),
            applies: container.querySelectorAll('.ui-apply, .power-apply-btn'), // 両方の適用ボタン
            reset: container.querySelector('.ui-reset'),
            exp: container.querySelector('.ui-exp'),
            keep: container.querySelector('.ui-keep'),
            scroll: container.querySelector('.ui-scroll-mode'), // 🌟追加
            ping: container.querySelector('.ui-ping'),     // 🌟追加
            lcd: document.getElementById(`lcd-${this.roleName}`)
        };

        // 🌟【修正】HTMLからのイベント呼び出し(onchange等)ができるように、DOMにインスタンスを紐付ける
        this.ui.box.vstInstance = this;

        this.bindEvents();
        setTimeout(() => this.syncOriginalConfigFromDOM(), 300);
        this.updateBaseVisual(this.conf);

        // 🚨【重要修正】DBを圧迫する元凶。MQTTで状態は取れるので、1分ごとのDBコマンド発行を停止します！
        // this.startPolling();

        // vst-unit-base.js のイベントバインド周辺
        this.ui.applies = container.querySelectorAll('.ui-apply, .power-apply-btn'); // 両方のクラスを取得

        // 状態変更があったときの処理内で
        this.ui.applies.forEach(btn => btn.classList.add('dirty'));

        // APPLYが押された後のリセット処理内で
        this.ui.applies.forEach(btn => {
            btn.classList.remove('dirty');
            btn.classList.add('success');
        });

    }

    renderFaceCenter() { return ``; }
    renderSettings() { return ``; }

    bindEvents() {
        this.ui.exp.onclick = () => this.toggleAccordion();
        this.ui.keep.onclick = () => this.toggleKeep();

        // 🌟 スクロールモード切替
        if (this.ui.scroll) {
            this.ui.scroll.onclick = () => {
                const isScroll = this.ui.lcd.classList.toggle('scroll-active');
                this.ui.scroll.classList.toggle('active', isScroll);
                if (isScroll) {
                    this.ui.lcd.style.overflowY = 'auto';
                    this.ui.lcd.scrollTop = this.ui.lcd.scrollHeight;
                } else {
                    this.ui.lcd.style.overflowY = 'hidden';
                }
            };
        }

        // 🌟 死活監視（Ping）
        if (this.ui.ping) {
            this.ui.ping.onclick = () => this.requestSync(false);
        }

        this.ui.reset.onclick = () => this.resetSettings();
        this.ui.sync.onclick = () => this.requestSync();
        this.ui.applies.forEach(btn => btn.onclick = () => this.applySettings());

        const inputs = document.querySelectorAll(`#vst-box-${this.roleName} .vst-input`);
        inputs.forEach(input => {
            input.addEventListener('change', () => this.checkDirtyState());
            input.addEventListener('input', () => this.checkDirtyState());
        });
    }

    updateBaseVisual(data) {
        if (data.updated_at || data.env_last_detect) {
            const d = new Date(data.updated_at || data.env_last_detect);
            this.updateDOMText(`base-time-${this.roleName}`, d.toLocaleTimeString('ja-JP', { hour12: false }));
        }

        if (data.val_status) {
            const statEl = document.getElementById(`base-status-${this.roleName}`);
            if (statEl) {
                const status = data.val_status.toUpperCase();
                statEl.innerText = status;
                statEl.style.color = (status === 'ALERT' || status === 'DETECT') ? 'var(--accent-red)' : 'var(--accent-green)';
            }
        }
        if (data.log_code) this.updateDOMText(`base-code-${this.roleName}`, `[${data.log_code}]`);
        if (data.log_msg) this.updateDOMText(`base-msg-${this.roleName}`, data.log_msg);
    }

    updateLCD(msg, logExt = null, isRed = false) {
        if (!this.ui.lcd) return;
        const t = new Date().toLocaleTimeString('ja-JP', { hour12: false });
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
        this.ui.applies.forEach(btn => { btn.classList.remove('dirty'); btn.classList.add('success'); btn.disabled = true; });

        try {
            const formData = new URLSearchParams();
            formData.append('sys_id', this.manager.nodeId);
            formData.append('cmd_type', 'update_config');
            const payload = { role: this.roleName };
            document.querySelectorAll(`#vst-box-${this.roleName} .vst-input`).forEach(input => {
                const key = input.getAttribute('data-key');
                if (key) payload[key] = input.type === 'checkbox' ? (input.checked ? 1 : 0) : parseFloat(input.value);
            });
            formData.append('cmd_json', JSON.stringify(payload));
            await fetch('api/send_cmd.php', { method: 'POST', body: formData });
        } catch (e) {} finally {
            this.ui.applies.forEach(btn => { btn.classList.remove('success'); btn.disabled = false; });
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