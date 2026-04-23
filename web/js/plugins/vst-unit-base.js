/**
 * WES 2026: VST Unit Base Class
 * 役割: 全プラグイン共通の基本機能（API通信、LCD表示、アコーディオン開閉、Ping同期）を提供する
 */
class VstUnitBase {
    constructor(conf, manager) {
        this.manager = manager;
        this.conf = conf;
        this.roleName = conf.vst_role_name;
        
        // 基本プロパティの初期化
        this.val_enabled = (parseInt(conf.val_enabled) === 1);
        
        // アコーディオンの表示モード (0: 手動, 1: キック時保持, 2: キック後5秒で自動閉)
        this.accordionMode = 2; 
        this.autoCloseTimer = null;
    }

    /**
     * 共通UI構造のビルド（各プラグインの initUI から呼ばれる）
     * Face（常時表示）と Accordion（詳細）の2段構成を構築する
     */
    buildBaseWrapper(faceHtml, accordionHtml) {
        const content = document.getElementById(`content-${this.roleName}`);
        if (!content) return;

        content.innerHTML = `
            <div class="vst-rack-panel">
                <div class="vst-face d-flex justify-content-between align-items-center p-2 border-bottom border-dark">
                    ${faceHtml}
                    
                    <div class="d-flex gap-1 align-items-center ms-auto">
                        <button class="btn-vst-icon text-warning" id="btn-ping-${this.roleName}" title="Ping / Sync">
                            <i class="fas fa-satellite-dish"></i>
                        </button>
                        <button class="btn-vst-icon text-info" id="btn-toggle-${this.roleName}" title="Details">
                            <i class="fas fa-chevron-down" id="icon-toggle-${this.roleName}"></i>
                        </button>
                    </div>
                </div>

                <div class="vst-accordion-content" id="accordion-${this.roleName}" style="display: none;">
                    <div class="d-flex gap-2 p-2 bg-dark">
                        <div class="lcd-monitor flex-grow-1 p-1">
                            <div class="lcd-header d-flex justify-content-between">
                                <span>STATUS_MONITOR</span>
                                <span id="lcd-time-${this.roleName}">--:--:--</span>
                            </div>
                            <div class="lcd-body mt-1">
                                <div id="lcd-msg-${this.roleName}">WAITING FOR SIGNAL...</div>
                                <div id="lcd-ext-${this.roleName}" class="lcd-ext mt-1 text-muted"></div>
                            </div>
                        </div>

                        <div class="vst-specific-settings d-flex flex-column gap-1" style="min-width: 120px;">
                            ${accordionHtml}
                        </div>
                    </div>
                </div>
            </div>
        `;

        // 共通イベントリスナーの登録
        document.getElementById(`btn-toggle-${this.roleName}`).onclick = () => this.toggleAccordion();
        document.getElementById(`btn-ping-${this.roleName}`).onclick = () => this.pingNode();
    }

    /**
     * アコーディオンの開閉制御
     */
    toggleAccordion(forceState = null) {
        const content = document.getElementById(`accordion-${this.roleName}`);
        const icon = document.getElementById(`icon-toggle-${this.roleName}`);
        if (!content || !icon) return;

        const isHidden = (content.style.display === "none");
        const willOpen = forceState !== null ? forceState : isHidden;

        if (willOpen) {
            content.style.display = "block";
            icon.className = "fas fa-chevron-up text-primary";
        } else {
            content.style.display = "none";
            icon.className = "fas fa-chevron-down text-info";
        }
    }

    /**
     * MQTTキック受信時のアコーディオン挙動
     */
    triggerKickDisplay() {
        if (this.accordionMode === 1) {
            this.toggleAccordion(true); // 開きっぱなし
        } else if (this.accordionMode === 2) {
            this.toggleAccordion(true); // 一時的に開く
            if (this.autoCloseTimer) clearTimeout(this.autoCloseTimer);
            this.autoCloseTimer = setTimeout(() => {
                this.toggleAccordion(false);
            }, 5000); // 5秒後に自動で閉じる
        }
    }

    /**
     * LCDモニターの更新
     */
    updateLCD(log_msg, log_code, log_ext, updated_at) {
        const timeEl = document.getElementById(`lcd-time-${this.roleName}`);
        const msgEl = document.getElementById(`lcd-msg-${this.roleName}`);
        const extEl = document.getElementById(`lcd-ext-${this.roleName}`);

        if (timeEl && updated_at) {
            // JSTに固定して時刻表示
            const d = new Date(updated_at);
            timeEl.innerText = d.toLocaleTimeString('ja-JP', { timeZone: 'Asia/Tokyo' });
        }
        
        if (msgEl) {
            const codeStr = log_code ? `[${log_code}] ` : "";
            msgEl.innerHTML = `${codeStr}${log_msg || "OK"}`;
        }

        if (extEl && log_ext) {
            // JSONオブジェクトをフォーマットして表示（スクロール可能）
            const extStr = typeof log_ext === 'object' ? JSON.stringify(log_ext, null, 1) : log_ext;
            extEl.innerText = extStr.replace(/[\{\}\"]/g, ''); // 見やすさのためにカッコを削る
        }

        // 更新をアピールするため一瞬色を変える
        const monitor = timeEl?.closest('.lcd-monitor');
        if (monitor) {
            monitor.style.boxShadow = "inset 0 0 10px var(--accent-green)";
            setTimeout(() => { monitor.style.boxShadow = "none"; }, 500);
        }
    }

    /**
     * NodeへのPing（死活・設定同期要求）送信
     */
    async pingNode() {
        const btn = document.getElementById(`btn-ping-${this.roleName}`);
        if (btn) btn.classList.add('vst-blink'); // 送信中アニメーション

        try {
            const formData = new URLSearchParams();
            formData.append('sys_id', this.manager.nodeId);
            formData.append('cmd_type', 'ping');
            formData.append('cmd_json', JSON.stringify({ role: this.roleName }));
            
            await fetch('api/send_cmd.php', { method: 'POST', body: formData });
            // 成功応答は update() で MQTT経由で非同期に受け取る
        } catch (e) {
            console.error(e);
        } finally {
            setTimeout(() => { if (btn) btn.classList.remove('vst-blink'); }, 1000);
        }
    }
}