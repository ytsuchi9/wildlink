/**
 * WildLink 2026 - System Unit Plugin
 * Role: system / node / main_manager
 */

// 親クラスの存在チェック（ロード順の安全策）
if (typeof VstUnitBase !== 'undefined') {

    class SystemUnit extends VstUnitBase {
        constructor(id, role, config) {
            super(id, role, config);
            this.type = 'SYSTEM';
            this.pollingMode = 'mqtt'; // default
        }

        /**
         * UIの生成
         */
        render(container) {
            const html = `
                <div class="vst-card system-card" id="vst-${this.role}">
                    <div class="vst-header">
                        <span class="vst-badge">SYSTEM</span>
                        <span class="vst-title">${this.config.name || 'メインシステム・ログ収集ユニット'}</span>
                    </div>
                    <div class="vst-body">
                        <div class="status-display">
                            <span class="status-label">STATUS:</span>
                            <span class="status-value" data-field="status">INITIALIZING...</span>
                        </div>
                        
                        <div class="control-group mt-3">
                            <label class="small text-muted d-block mb-1">LOG COLLECTION MODE</label>
                            <div class="btn-group btn-group-sm w-100" role="group">
                                <button type="button" class="btn btn-outline-primary active" id="btn-mode-mqtt-${this.role}" onclick="vstUpdateMode('${this.role}', 'mqtt')">MQTT Kick</button>
                                <button type="button" class="btn btn-outline-primary" id="btn-mode-poll-${this.role}" onclick="vstUpdateMode('${this.role}', 'poll')">Polling</button>
                            </div>
                        </div>

                        <div class="info-grid mt-3">
                            <div class="info-item">
                                <span class="label">CPU</span>
                                <span class="value" data-field="cpu_t">--</span>°C
                            </div>
                            <div class="info-item">
                                <span class="label">UPTIME</span>
                                <span class="value" data-field="uptime">--</span>
                            </div>
                        </div>
                    </div>
                    <div class="vst-footer">
                        <div class="log-mini-view" id="log-${this.role}">
                            Waiting for logs...
                        </div>
                    </div>
                </div>
            `;
            container.insertAdjacentHTML('beforeend', html);
        }

        /**
         * 状態更新時の処理
         */
        onUpdate(data) {
            const card = document.getElementById(`vst-${this.role}`);
            if (!card) return;

            const statusEl = card.querySelector('[data-field="status"]');
            const cpuEl = card.querySelector('[data-field="cpu_t"]');
            const uptimeEl = card.querySelector('[data-field="uptime"]');
            
            if (statusEl) statusEl.textContent = (data.val_status || 'UNKNOWN').toUpperCase();
            if (cpuEl && data.sys_cpu_t) cpuEl.textContent = data.sys_cpu_t;
            if (uptimeEl && data.sys_up) uptimeEl.textContent = data.sys_up;

            // ステータスに応じた色変更
            if (data.val_status === 'active' || data.val_status === 'online') {
                statusEl.className = 'status-value text-success';
            } else if (data.val_status === 'error' || data.val_status === 'offline') {
                statusEl.className = 'status-value text-danger';
            }
        }
    }

    // グローバルなモード切替関数（簡易実装）
    window.vstUpdateMode = function(role, mode) {
        console.log(`[System] Switching ${role} to ${mode} mode`);
        const mqttBtn = document.getElementById(`btn-mode-mqtt-${role}`);
        const pollBtn = document.getElementById(`btn-mode-poll-${role}`);
        
        if (mode === 'mqtt') {
            mqttBtn.classList.add('active');
            pollBtn.classList.remove('active');
        } else {
            pollBtn.classList.add('active');
            mqttBtn.classList.remove('active');
        }
        // ここで実際のMQTTコマンドやAPIリクエストを発火させる処理を追加可能
    };

    // 登録
    VstManager.registerPlugin('system', SystemUnit);
    VstManager.registerPlugin('node', SystemUnit);

} else {
    console.error("[SystemUnit] VstUnitBase is not defined. Check load order.");
}