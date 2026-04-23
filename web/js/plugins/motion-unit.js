/**
 * WES 2026: MotionUnit (Inherits VstUnitBase)
 * 役割: モーションセンサーのUIを構築。アコーディオン機能に対応。
 */
class MotionUnit extends VstUnitBase {
    constructor(conf, manager) {
        super(conf, manager);
        // DBからの初期値
        this.act_rec = (conf.val_params?.act_rec === 1 || conf.val_params?.act_rec === true);
        this.val_interval = parseFloat(conf.val_params?.val_interval || 15.0);
        this.lastDetectTime = "---";
    }

    initUI() {
        // --- 1. Face (常時表示する1/2 Uの顔) ---
        const faceHtml = `
            <div class="d-flex align-items-center gap-2">
                <div id="led-${this.roleName}" class="status-led ${this.val_enabled ? 'led-on' : 'led-off'}"></div>
                <div class="form-check form-switch m-0" title="Unit Power">
                    <input class="form-check-input" type="checkbox" id="en-sw-${this.roleName}" ${this.val_enabled ? 'checked' : ''}>
                </div>
            </div>
            
            <div class="d-flex align-items-center gap-2 flex-grow-1 justify-content-center text-center">
                <i id="icon-${this.roleName}" class="fas fa-walking" style="font-size: 1.2rem; color: var(--text-dim);"></i>
                <span id="stat-${this.roleName}" class="font-monospace fw-bold" style="font-size: 0.8rem; color: ${this.val_enabled ? 'var(--accent-green)' : '#555'};">
                    ${this.val_enabled ? 'SCANNING' : 'PAUSED'}
                </span>
            </div>
        `;

        // --- 2. Accordion (展開時の詳細設定) ---
        const accordionHtml = `
            <div class="rack-param-row">
                <label>REC DB</label>
                <input type="checkbox" id="rec-sw-${this.roleName}" ${this.act_rec ? 'checked' : ''}>
            </div>
            <div class="rack-param-row">
                <label>HOLD (sec)</label>
                <input type="number" id="int-val-${this.roleName}" class="form-control-vst" value="${this.val_interval}">
            </div>
            <div class="d-flex gap-1 mt-auto pt-2">
                <button class="btn btn-warning btn-sm flex-fill" id="btn-reset-${this.roleName}"><i class="fas fa-undo"></i></button>
                <button class="btn btn-primary btn-sm flex-fill fw-bold" id="btn-apply-${this.roleName}">APPLY</button>
            </div>
        `;

        // 親クラスのビルド関数を呼び出してDOMを生成
        this.buildBaseWrapper(faceHtml, accordionHtml);

        // --- 3. 個別イベントリスナーの登録 ---
        document.getElementById(`btn-apply-${this.roleName}`).onclick = () => this.applySettings();
        document.getElementById(`btn-reset-${this.roleName}`).onclick = () => this.resetSettings();
        
        // スイッチ即時反映（見た目のみ。DB確定はMQTTキック後）
        document.getElementById(`en-sw-${this.roleName}`).onchange = (e) => {
            this.val_enabled = e.target.checked;
            this.updateFaceVisual();
        };
    }

    updateFaceVisual() {
        const ledEl  = document.getElementById(`led-${this.roleName}`);
        const statEl = document.getElementById(`stat-${this.roleName}`);
        const pluginEl = document.getElementById(`plugin-${this.roleName}`);

        if (this.val_enabled) {
            pluginEl?.classList.remove('unit-disabled');
            if (ledEl) ledEl.className = 'status-led led-on';
            if (statEl && statEl.innerText !== "DETECTED") { 
                statEl.innerText = "SCANNING"; 
                statEl.style.color = "var(--accent-green)"; 
            }
        } else {
            pluginEl?.classList.add('unit-disabled');
            if (ledEl) ledEl.className = 'status-led led-off';
            if (statEl) { 
                statEl.innerText = "PAUSED"; 
                statEl.style.color = "#555"; 
            }
        }
    }

    async applySettings() {
        const isRec    = document.getElementById(`rec-sw-${this.roleName}`).checked;
        const interval = parseFloat(document.getElementById(`int-val-${this.roleName}`).value);

        try {
            const formData = new URLSearchParams();
            formData.append('sys_id', this.manager.nodeId);
            formData.append('cmd_type', 'update_config');
            // CRUD概念に基づくパッチ送信
            formData.append('cmd_json', JSON.stringify({
                role: this.roleName,
                val_enabled: this.val_enabled ? 1 : 0,
                val_params: { act_rec: isRec ? 1 : 0, val_interval: interval }
            }));

            await fetch('api/send_cmd.php', { method: 'POST', body: formData });
            // 送信完了後、LCDを一時的に開いて結果を待つ
            this.triggerKickDisplay(); 
        } catch (e) {
            console.error("Apply Error:", e);
        }
    }

    /**
     * MQTT経由でHub/Nodeからステータス更新を受信した際の処理
     */
    update(data) {
        // ベースクラスのLCD更新機能を呼び出す
        this.updateLCD(data.log_msg, data.log_code, data.log_ext || data.val_params, data.updated_at);

        // パラメータの同期
        const ext = data.log_ext || data.val_params;
        if (ext) {
            if (ext.act_rec !== undefined) {
                this.act_rec = (ext.act_rec === 1 || ext.act_rec === true);
                document.getElementById(`rec-sw-${this.roleName}`).checked = this.act_rec;
            }
            if (ext.val_interval !== undefined) {
                this.val_interval = ext.val_interval;
                document.getElementById(`int-val-${this.roleName}`).value = this.val_interval;
            }
        }

        // val_enabledの同期と見た目の更新
        if (data.val_enabled !== undefined) {
            this.val_enabled = (parseInt(data.val_enabled) === 1);
            document.getElementById(`en-sw-${this.roleName}`).checked = this.val_enabled;
        }
        this.updateFaceVisual();

        // 成功を検知したらアコーディオンを開く(設定時間で閉じる)
        if (data.cmd_status === 'completed' || data.val_status === 'synced') {
            this.triggerKickDisplay();
        }
    }

    /**
     * 物理的なイベント（検知など）を受信した際の処理
     */
    onEvent(data) {
        if (!this.val_enabled) return;

        const icon = document.getElementById(`icon-${this.roleName}`);
        const stat = document.getElementById(`stat-${this.roleName}`);

        if (data.event === 'motion_detected' || data.val_status === 'detected') {
            if (icon) { icon.style.color = "var(--accent-red)"; icon.classList.add('vst-blink'); }
            if (stat) { stat.innerText = "DETECTED"; stat.style.color = "var(--accent-red)"; }
            
            // 検知イベントのログをLCDにも表示し、アコーディオンを開いて知らせる
            this.updateLCD("MOTION DETECTED!", 200, data.log_ext, data.created_at);
            this.triggerKickDisplay();

        } else if (data.val_status === 'idle') {
            if (icon) { icon.style.color = "var(--text-dim)"; icon.classList.remove('vst-blink'); }
            if (stat) { stat.innerText = "SCANNING"; stat.style.color = "var(--accent-green)"; }
        }
    }
}