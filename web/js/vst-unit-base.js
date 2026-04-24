/**
 * WES 2026: VstUnitBase (Responsive Rack System)
 * 離散的なアスペクト比(1U/2U/3U)と可変フォントを実装
 */
class VstUnitBase {
    constructor(conf, manager) {
        this.manager = manager;
        this.conf = conf;
        this.roleName = conf.vst_role_name;
        this.val_enabled = (parseInt(conf.val_enabled) === 1);
        this.originalConfig = {};
        this.accordionMode = 2;
        this.autoCloseTimer = null;
    }

    /**
     * [buildBaseWrapper]
     * 縦横比とフォントサイズを動的に管理するベース構造
     */
    buildBaseWrapper(faceCenterHtml, accordionHtml) {
        const content = document.getElementById(`content-${this.roleName}`);
        if (!content) return;

        // 🌟 1Uの概念をCSS変数で定義。aspect-ratioで高さを自動計算。
        // min-widthを下回るとスクロールバーが出るよう親で制御することを想定
        content.innerHTML = `
            <div class="vst-rack-unit mb-3" id="panel-${this.roleName}" 
                 style="--u-base-font: clamp(0.7rem, 1.5vw, 1rem); 
                        min-width: 320px; 
                        background: #1a1a1a; 
                        border: 2px solid #333; 
                        border-radius: 4px; 
                        overflow: hidden; 
                        font-size: var(--u-base-font);">
                
                <div class="vst-face-1u" 
                     style="display: flex; align-items: center; justify-content: space-between; 
                            padding: 0 1rem; height: auto; min-height: 4rem;
                            background: linear-gradient(180deg, #2a2a2a 0%, #151515 100%);">
                    
                    <div style="display: flex; align-items: center; width: 25%; flex-shrink: 0;">
                        <div id="led-${this.roleName}" class="status-led ${this.val_enabled ? 'led-on' : 'led-off'}" 
                             style="width: 0.8rem; height: 0.8rem; margin-right: 0.8rem;"></div>
                        <span style="font-weight: 800; color: #888; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            ${this.roleName.replace('vst_', '').toUpperCase()}
                        </span>
                    </div>
                    
                    <div style="flex-grow: 1; display: flex; justify-content: center; overflow: hidden; padding: 0 0.5rem;">
                        ${faceCenterHtml}
                    </div>
                    
                    <div style="display: flex; align-items: center; justify-content: flex-end; width: 35%; flex-shrink: 0; gap: 1rem;">
                        <button class="btn btn-warning btn-sm fw-bold d-none apply-pulse" id="btn-apply-${this.roleName}" 
                                style="font-size: 0.7rem; padding: 0.2rem 0.5rem;">APPLY</button>
                        
                        <div class="form-check form-switch m-0">
                            <input class="form-check-input vst-input" type="checkbox" id="en-sw-${this.roleName}" data-key="val_enabled" 
                                   ${this.val_enabled ? 'checked' : ''} style="cursor: pointer;">
                        </div>
                        
                        <div style="display: flex; gap: 0.5rem; border-left: 1px solid #444; padding-left: 0.8rem;">
                            <button class="btn-vst-icon text-warning" id="btn-ping-${this.roleName}"><i class="fas fa-satellite-dish"></i></button>
                            <button class="btn-vst-icon text-info" id="btn-toggle-${this.roleName}"><i class="fas fa-chevron-down" id="icon-toggle-${this.roleName}"></i></button>
                        </div>
                    </div>
                </div>

                <div id="accordion-${this.roleName}" style="display: none; background: #000; border-top: 2px solid #333;">
                    <div class="container-fluid p-0">
                        <div class="row g-0">
                            <div class="col-12 col-lg-8 border-end border-dark">
                                <div id="lcd-frame-${this.roleName}" 
                                     style="min-height: 12rem; display: flex; flex-direction: column; padding: 0.5rem;">
                                    <div class="d-flex justify-content-between" style="font-size: 0.6rem; color: #555; margin-bottom: 0.3rem;">
                                        <span>SIGNAL_PROCESSOR</span>
                                        <span id="lcd-time-${this.roleName}">--:--:--</span>
                                    </div>
                                    <div class="lcd-body" style="flex-grow: 1; background: #050505; border: 1px solid #222; padding: 0.5rem; border-radius: 2px;">
                                        <div id="lcd-msg-${this.roleName}" style="color: #0f0; font-family: monospace; font-size: 1.1rem;">IDLE</div>
                                        <div id="lcd-ext-${this.roleName}" class="mt-2 text-info" style="font-size: 0.8rem; font-family: monospace;"></div>
                                    </div>
                                </div>
                            </div>
                            <div class="col-12 col-lg-4 bg-dark p-3">
                                <div style="font-size: 0.65rem; color: #888; text-transform: uppercase; margin-bottom: 1rem;">Parameters</div>
                                ${accordionHtml}
                                <div class="mt-4 pt-2 border-top border-secondary">
                                    <button class="btn btn-outline-secondary btn-sm w-100" id="btn-reset-${this.roleName}" style="font-size: 0.7rem;">REVERT</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        this.bindCommonEvents();
        this.bindDirtyCheck();
        
        // 🌟 APPLY点滅対策：HTMLが落ち着くのをしっかり待ってから「正本」を取得
        setTimeout(() => this.syncOriginalConfigFromDOM(), 300);
    }

    /**
     * [syncOriginalConfigFromDOM]
     * 点滅防止：すべての値を文字列かつ空白削除で厳密に管理
     */
    syncOriginalConfigFromDOM() {
        this.originalConfig = {};
        const inputs = document.querySelectorAll(`#content-${this.roleName} .vst-input`);
        inputs.forEach(input => {
            const key = input.getAttribute('data-key');
            if (key) this.originalConfig[key] = this.getVal(input);
        });
        this.checkDirtyState();
    }

    getVal(input) {
        if (input.type === 'checkbox') return input.checked ? "1" : "0";
        return String(input.value).trim();
    }

    /**
     * [checkDirtyState]
     * 変更された項目のみ背景を変える（全体が変わらないように制御）
     */
    checkDirtyState() {
        let isDirty = false;
        const inputs = document.querySelectorAll(`#content-${this.roleName} .vst-input`);
        
        inputs.forEach(input => {
            const key = input.getAttribute('data-key');
            if (!key) return;

            const current = this.getVal(input);
            const original = this.originalConfig[key];

            if (current !== original) {
                isDirty = true;
                // 🌟 個別の項目だけ背景を変える
                input.style.backgroundColor = "rgba(255, 193, 7, 0.2)";
                if (input.type !== 'checkbox') input.style.color = "#ffc107";
            } else {
                input.style.backgroundColor = "";
                input.style.color = "";
            }
        });

        const btn = document.getElementById(`btn-apply-${this.roleName}`);
        if (btn) {
            if (isDirty) btn.classList.remove('d-none');
            else btn.classList.add('d-none');
        }
    }

    /**
     * [updateLCD]
     * 検知時の派手な演出
     */
    updateLCD(log_msg, log_code, log_ext, updated_at) {
        const msgEl = document.getElementById(`lcd-msg-${this.roleName}`);
        const frame = document.getElementById(`lcd-frame-${this.roleName}`);
        
        if (msgEl) {
            msgEl.innerHTML = log_msg || "OK";
            // 🌟 検知時は背景を一瞬赤くフラッシュさせる（派手な通知）
            if (log_msg && (log_msg.includes('DETECTION') || log_msg.includes('ON'))) {
                if (frame) {
                    frame.style.backgroundColor = "rgba(255, 0, 0, 0.3)";
                    setTimeout(() => { frame.style.backgroundColor = ""; }, 500);
                }
            }
        }
        
        const timeEl = document.getElementById(`lcd-time-${this.roleName}`);
        if (timeEl && updated_at) {
            timeEl.innerText = new Date(updated_at).toLocaleTimeString('ja-JP');
        }
        const extEl = document.getElementById(`lcd-ext-${this.roleName}`);
        if (extEl && log_ext) {
            const extStr = typeof log_ext === 'object' ? JSON.stringify(log_ext) : log_ext;
            extEl.innerText = String(extStr).replace(/[\{\}\"]/g, '');
        }
    }

    // --- 以降、基本メソッド ---
    bindCommonEvents() {
        document.getElementById(`btn-toggle-${this.roleName}`).onclick = () => this.toggleAccordion();
        document.getElementById(`btn-ping-${this.roleName}`).onclick = () => this.pingNode();
        document.getElementById(`btn-apply-${this.roleName}`).onclick = () => this.applySettings();
        document.getElementById(`btn-reset-${this.roleName}`).onclick = () => this.resetSettings();
    }

    bindDirtyCheck() {
        const inputs = document.querySelectorAll(`#content-${this.roleName} .vst-input`);
        inputs.forEach(input => {
            input.addEventListener('change', () => this.checkDirtyState());
            input.addEventListener('input', () => this.checkDirtyState());
        });
    }

    toggleAccordion(forceState = null) {
        const content = document.getElementById(`accordion-${this.roleName}`);
        const icon = document.getElementById(`icon-toggle-${this.roleName}`);
        if (!content || !icon) return;
        const isHidden = (content.style.display === "none");
        const willOpen = forceState !== null ? forceState : isHidden;
        content.style.display = willOpen ? "block" : "none";
        icon.className = willOpen ? "fas fa-chevron-up text-primary" : "fas fa-chevron-down text-info";
    }

    resetSettings() {
        const inputs = document.querySelectorAll(`#content-${this.roleName} .vst-input`);
        inputs.forEach(input => {
            const key = input.getAttribute('data-key');
            if (!key || this.originalConfig[key] === undefined) return;
            if (input.type === 'checkbox') {
                input.checked = (String(this.originalConfig[key]) === "1");
            } else {
                input.value = this.originalConfig[key];
            }
        });
        this.checkDirtyState();
    }

    async pingNode() {
        const btn = document.getElementById(`btn-ping-${this.roleName}`);
        if (btn) btn.classList.add('vst-blink');
        try {
            const formData = new URLSearchParams();
            formData.append('sys_id', this.manager.nodeId);
            formData.append('cmd_type', 'ping');
            formData.append('cmd_json', JSON.stringify({ role: this.roleName }));
            await fetch('api/send_cmd.php', { method: 'POST', body: formData });
        } catch (e) { console.error(e); } finally {
            setTimeout(() => { if (btn) btn.classList.remove('vst-blink'); }, 1000);
        }
    }
}