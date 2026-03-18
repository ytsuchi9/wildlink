// js/plugins/sensor-unit.js
class SensorUnit {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        // 2026年仕様: vst_type ではなく vst_role_name をキーにする
        this.name = conf.vst_role_name || conf.vst_type;
        
        // すでに VstManager でデコード済みの想定だが、念のためガード
        this.params = (typeof conf.val_params === 'string') 
            ? JSON.parse(conf.val_params || '{}') 
            : (conf.val_params || {});
    }

    initUI() {
        const content = document.getElementById(`content-${this.name}`);
        if (!content) return;

        // センサー用の大きな数値表示エリアを作成
        // 単位やラベルも params から動的に取得
        const unit = this.params.unit || '';
        const label = this.params.label || '';

        content.innerHTML = `
            <div class="sensor-container" style="text-align: center; padding: 10px 0;">
                <div class="sensor-label" style="font-size: 0.8rem; opacity: 0.7;">${label}</div>
                <div class="sensor-value" style="font-size: 2.2rem; font-weight: bold; color: var(--accent-color, #00ffcc);">
                    <span id="val-${this.name}">--</span>
                    <span style="font-size: 1rem; margin-left: 4px;">${unit}</span>
                </div>
            </div>
        `;
    }

    /**
     * @param {Object} unitData - { val_status, env }
     */
    update(unitData) {
        const valEl = document.getElementById(`val-${this.name}`);
        const disp = document.getElementById(`disp-${this.name}`);
        if (!valEl || !disp) return;

        // 1. 動作状態（生存確認）の更新
        disp.innerText = (unitData.val_status || "IDLE").toUpperCase();
        
        // 2. 数値の更新
        // unitData.env には node_data から取得した JSON 配列が入っている想定
        let value = '--';

        if (unitData.env) {
            // Role名に合致するデータ、または汎用的なキーを探す
            // 例: { "temp": 24.5, "humi": 60 } のような構造
            value = unitData.env[this.name] 
                 || unitData.env['value'] 
                 || unitData.env['temp'] 
                 || unitData.env['val'] 
                 || '--';
        }

        // 数値なら小数点第1位までに整形
        if (value !== '--' && !isNaN(value)) {
            value = parseFloat(value).toFixed(1);
            
            // 閾値チェック（遊び心: 高温時に色を変えるなど）
            if (this.params.threshold && value > this.params.threshold) {
                valEl.style.color = "#ff4444";
            } else {
                valEl.style.color = "";
            }
        }

        valEl.innerText = value;
    }
}