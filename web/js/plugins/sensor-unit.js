/**
 * WildLink 2026 | Sensor Unit Plugin
 * 役割: 数値データの表示と閾値によるアラート表示
 */
class SensorUnit {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        // Role名を一貫して使用
        this.roleName = conf.vst_role_name;
        
        // パラメータの安全なデコード
        try {
            this.params = (typeof conf.val_params === 'string') 
                ? JSON.parse(conf.val_params || '{}') 
                : (conf.val_params || {});
        } catch (e) {
            console.error(`[SensorUnit] Param parse error for ${this.roleName}:`, e);
            this.params = {};
        }
    }

    /**
     * VstManagerから描画直後に呼ばれる初期化処理
     */
    initUI() {
        const content = document.getElementById(`content-${this.roleName}`);
        if (!content) return;

        // params から表示用の設定を取得（DBの val_params に記述しておく想定）
        const unit = this.params.unit || '';   // 例: "°C", "%", "hPa"
        const label = this.params.label || ''; // 例: "Ambient Temp"

        content.innerHTML = `
            <div class="sensor-container" style="text-align: center; padding: 15px 0;">
                <div class="sensor-label" style="font-size: 0.75rem; opacity: 0.6; text-transform: uppercase; letter-spacing: 1px;">
                    ${label}
                </div>
                <div class="sensor-value-wrapper" style="margin-top: 5px;">
                    <span id="val-${this.roleName}" style="font-size: 2.4rem; font-weight: bold; color: var(--accent-color, #00ffcc); font-family: 'Share Tech Mono', monospace;">
                        --
                    </span>
                    <span style="font-size: 1rem; margin-left: 5px; opacity: 0.8;">${unit}</span>
                </div>
            </div>
        `;
        
        console.log(`[SensorUnit] UI Initialized: ${this.roleName}`);
    }

    /**
     * VstManagerのリフレッシュループから呼ばれる更新処理
     * @param {Object} unitData - { val_status, env }
     */
    update(unitData) {
        const valEl = document.getElementById(`val-${this.roleName}`);
        const statusEl = document.getElementById(`disp-${this.roleName}`);
        if (!valEl) return;

        // 1. ステータステキストの更新 (ONLINE/OFFLINE/IDLE等)
        if (statusEl) {
            statusEl.innerText = (unitData.val_status || "IDLE").toUpperCase();
        }
        
        // 2. センサー数値の抽出
        let value = '--';

        if (unitData.env) {
            /**
             * データの優先順位:
             * 1. env[roleName] : Role名に直結したデータ (推奨)
             * 2. env['value']  : 汎用キー
             * 3. env['temp']...: 代表的なセンサー名
             */
            value = unitData.env[this.roleName] 
                 ?? unitData.env['value'] 
                 ?? unitData.env['temp'] 
                 ?? unitData.env['val'] 
                 ?? '--';
        }

        // 3. 数値の整形とアラート表示
        if (value !== '--' && !isNaN(value)) {
            const numValue = parseFloat(value);
            value = numValue.toFixed(1);
            
            // 閾値チェック（val_paramsに "threshold": 40 等があれば発動）
            if (this.params.threshold && numValue >= this.params.threshold) {
                valEl.style.color = "#ff4444"; // アラート色
                valEl.classList.add('vst-blink'); // 点滅アニメーション（CSSにある想定）
            } else {
                valEl.style.color = "";
                valEl.classList.remove('vst-blink');
            }
        }

        valEl.innerText = value;
    }
}

// グローバルスコープに登録（VstManagerが window["SensorUnit"] で見つけられるようにする）
window.SensorUnit = SensorUnit;