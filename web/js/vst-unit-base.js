/**
 * WES 2026: VstUnitBase (Rack System v17 Core)
 * V17のCSS構造と通信ロジックを統合した共通基盤クラス
 */
class VstUnitBase {
    constructor(conf, manager) {
        this.manager = manager;
        this.conf = Object.assign({
            vst_description: 'Unit', vst_role_name: 'vst_0', sys_id: 'sys_0', loc_name: 'UNKNOWN',
            val_enabled: 1, val_status: 'IDLE', log_msg: 'Ready.', log_code: 200
        }, conf);
        
        this.roleName = this.conf.vst_role_name;
        this.sysId = this.conf.sys_id;
        this.val_enabled = (parseInt(this.conf.val_enabled) === 1);
        
        this.originalConfig = {};
        this.isExpanded = false;
        this.isKeep = false;
        this.isDirty = false;
        this.ui = {};

        this.injectIndicatorStyles();
    }

    // 各プラグインから呼ばれる初期化関数
    initUI() {
        const container = document.getElementById(`content-${this.roleName}`);
        if (!container) return;

        // VstManagerが自動生成した余分なヘッダー等を隠し、V17の純粋な外観にする
        const pluginWrapper = document.getElementById(`plugin-${this.roleName}`);
        if (pluginWrapper) {
            pluginWrapper.className = ''; 
            const header = pluginWrapper.querySelector('.plugin-header');
            if (header) header.style.display = 'none';
        }

        // V17の骨格を生成
        container.innerHTML = `
            <div class="vst-unit-box" id="vst-box-${this.roleName}">
                <div class="vst-unit-face">
                    <div class="face-left">
                        <label class="power-switch-v">
                            <input type="checkbox" class="ui-sw vst-input" data-key="val_enabled" ${this.val_enabled ? 'checked' : ''}>
                            <span class="slider"></span>
                        </label>
                        <button class="btn-vst apply-btn-mini ui-apply">APPLY</button>
                    </div>
                    <div class="face-center" id="face-center-${this.roleName}">
                        ${this.renderFaceCenter()}
                    </div>
                    <div class="face-right">
                        <button class="icon-btn ui-exp" style="font-size:2.5cqi;">⛶</button>
                        <button class="icon-btn ui-keep" style="font-size:1.6cqi;">固定</button>
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

        this.ui = {
            box: document.getElementById(`vst-box-${this.roleName}`),
            sw: container.querySelector('.ui-sw'),
            applies: container.querySelectorAll('.ui-apply'),
            reset: container.querySelector('.ui-reset'),
            exp: container.querySelector('.ui-exp'),
            keep: container.querySelector('.ui-keep'),
            lcd: document.getElementById(`lcd-${this.roleName}`)
        };

        this.bindEvents();
        setTimeout(() => this.syncOriginalConfigFromDOM(), 300);
    }

    // 子クラスでオーバーライドする描画関数
    renderFaceCenter() { return ``; }
    renderSettings() { return ``; }

    // --- ロジック・イベント基盤 ---
    bindEvents() {
        this.ui.exp.onclick = () => this.toggleAccordion();
        this.ui.keep.onclick = () => this.toggleKeep();
        this.ui.reset.onclick = () => this.resetSettings();
        this.ui.applies.forEach(btn => btn.onclick = () => this.applySettings());

        const inputs = document.querySelectorAll(`#vst-box-${this.roleName} .vst-input`);
        inputs.forEach(input => {
            input.addEventListener('change', () => this.checkDirtyState());
            input.addEventListener('input', () => this.checkDirtyState());
        });
    }

    syncOriginalConfigFromDOM() {
        this.originalConfig = {};
        const inputs = document.querySelectorAll(`#vst-box-${this.roleName} .vst-input`);
        inputs.forEach(input => {
            const key = input.getAttribute('data-key');
            if (key) this.originalConfig[key] = input.type === 'checkbox' ? (input.checked ? "1" : "0") : String(input.value).trim();
        });
        this.checkDirtyState();
    }

    checkDirtyState() {
        this.isDirty = false;
        const inputs = document.querySelectorAll(`#vst-box-${this.roleName} .vst-input`);
        
        inputs.forEach(input => {
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
        const inputs = document.querySelectorAll(`#vst-box-${this.roleName} .vst-input`);
        inputs.forEach(input => {
            const key = input.getAttribute('data-key');
            if (!key || this.originalConfig[key] === undefined) return;
            if (input.type === 'checkbox') input.checked = (this.originalConfig[key] === "1");
            else input.value = this.originalConfig[key];
        });
        this.checkDirtyState();
    }

    async applySettings() {
        if (!this.isDirty) return;
        this.triggerAlert('YELLOW', 'SYNCING...');
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
        } catch (e) {
            console.error("Apply Error:", e);
        } finally {
            this.ui.applies.forEach(btn => { btn.classList.remove('success'); btn.disabled = false; });
        }
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

    // --- ユーティリティ系 ---
    updateLCD(msg, isRed = false) {
        if (!this.ui.lcd) return;
        const t = new Date().toLocaleTimeString('ja-JP', { hour12: false });
        const color = isRed ? 'var(--accent-red)' : 'var(--accent-green)';
        this.ui.lcd.innerHTML += `<br><span style="color:#555;">[${t}]</span> <span style="color:${color};">${msg}</span>`;
        this.ui.lcd.scrollTop = this.ui.lcd.scrollHeight;
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

    // インジケーター用の極小CSSを動的に注入（CSSファイルを汚さないため）
    injectIndicatorStyles() {
        if (document.getElementById('vst-ind-styles')) return;
        const style = document.createElement('style');
        style.id = 'vst-ind-styles';
        style.innerHTML = `
            .ind-led { display:inline-block; padding:0 0.4cqi; margin-right:0.3cqi; border:1px solid #444; border-radius:2px; font-size:1.4cqi; background:#222; color:#555; transition:0.2s; }
            .ind-led.on { border-color:var(--accent-green); color:var(--accent-green); background:rgba(0,255,65,0.1); box-shadow:0 0 3px rgba(0,255,65,0.4); }
            .ind-led.red { border-color:var(--accent-red); color:var(--accent-red); background:rgba(255,0,0,0.1); box-shadow:0 0 3px rgba(255,0,0,0.4); }
            .ind-val { display:inline-block; padding:0 0.4cqi; margin-right:0.3cqi; font-size:1.4cqi; color:#aaa; background:#111; border-bottom:1px solid #444; }
        `;
        document.head.appendChild(style);
    }
}