/**
 * WildLink 2026 | MotionUnit Plugin (WES 2026 準拠)
 * 役割: 人感センサーの検知状態をリアルタイムに表示し、履歴（最終検知時刻）を管理する
 */
class MotionUnit {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        this.roleName = conf.vst_role_name;
        
        // パラメータの取得（閾値設定などがあれば拡張可能）
        this.params = (typeof conf.val_params === 'string') 
            ? JSON.parse(conf.val_params || '{}') 
            : (conf.val_params || {});

        this.lastDetectTime = "---";
    }

    /**
     * VstManagerから描画直後に呼ばれる初期化処理
     * UIの骨格を作成する
     */
    initUI() {
        const content = document.getElementById(`content-${this.roleName}`);
        if (!content) return;

        content.innerHTML = `
            <div class="motion-container" style="text-align: center; padding: 10px 0;">
                <div id="icon-${this.roleName}" class="motion-icon" style="font-size: 2.5rem; color: #333; transition: all 0.3s ease;">
                    <i class="fas fa-running"></i>
                </div>
                
                <div id="stat-${this.roleName}" style="font-size: 0.8rem; font-weight: bold; margin-top: 5px; color: #888;">
                    SCANNING...
                </div>

                <div style="margin-top: 10px; border-top: 1px solid #333; padding-top: 5px;">
                    <span style="font-size: 0.6rem; opacity: 0.5; display: block; text-transform: uppercase;">Last Detection</span>
                    <span id="time-${this.roleName}" style="font-size: 0.9rem; font-family: 'Share Tech Mono', monospace; color: #00ffcc;">
                        ${this.lastDetectTime}
                    </span>
                </div>
            </div>
        `;
        
        console.log(`[MotionUnit] UI Initialized: ${this.roleName}`);
    }

    /**
     * MQTTイベント(WES 2026準拠)を受信した際の処理
     * @param {Object} data - { event, val_status, log_code, env_last_detect, ... }
     */
    onEvent(data) {
        console.log(`[MotionUnit:${this.roleName}] Event Received:`, data);

        if (data.event === 'motion_detected') {
            this.handleDetection(data);
        } else if (data.val_status === 'idle') {
            this.handleReset();
        }
    }

    /**
     * 検知時のUIエフェクト
     */
    handleDetection(data) {
        const icon = document.getElementById(`icon-${this.roleName}`);
        const stat = document.getElementById(`stat-${this.roleName}`);
        const timeEl = document.getElementById(`time-${this.roleName}`);
        const pluginEl = document.getElementById(`plugin-${this.roleName}`);

        // 1. 最終検知時刻の更新
        if (data.env_last_detect) {
            const dt = new Date(data.env_last_detect);
            this.lastDetectTime = dt.toLocaleTimeString('ja-JP');
            if (timeEl) timeEl.innerText = this.lastDetectTime;
        }

        // 2. 視覚的アラート (赤く光らせる)
        if (icon) {
            icon.style.color = "#ff4444";
            icon.style.transform = "scale(1.2)";
            icon.classList.add('vst-blink'); // CSSで定義された点滅アニメーション
        }
        if (stat) {
            stat.innerText = "MOTION DETECTED!";
            stat.style.color = "#ff4444";
        }
        if (pluginEl) {
            pluginEl.classList.add('u-error'); // 枠線を赤くする等の強調
        }
    }

    /**
     * 待機状態(idle)への復帰
     */
    handleReset() {
        const icon = document.getElementById(`icon-${this.roleName}`);
        const stat = document.getElementById(`stat-${this.roleName}`);
        const pluginEl = document.getElementById(`plugin-${this.roleName}`);

        if (icon) {
            icon.style.color = "#333";
            icon.style.transform = "scale(1.0)";
            icon.classList.remove('vst-blink');
        }
        if (stat) {
            stat.innerText = "SCANNING...";
            stat.style.color = "#888";
        }
        if (pluginEl) {
            pluginEl.classList.remove('u-error');
        }
    }

    /**
     * 定期ポーリング(DB経由)によるバックアップ更新
     */
    update(unitData) {
        // MQTTが切断されている場合や、ページ読み込み直後の初期化に使用
        if (unitData.val_status === 'detected') {
            // ポーリングデータ内に最終検知時刻があれば反映
            const mockEvent = {
                event: 'sync',
                env_last_detect: unitData.env_last_detect,
                val_status: 'detected'
            };
            this.handleDetection(mockEvent);
        } else {
            this.handleReset();
        }
    }
}

// VstManagerが見つけられるようにグローバル登録
window.MotionUnit = MotionUnit;