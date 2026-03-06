// js/plugins/sensor-unit.js
class SensorUnit {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        this.name = conf.vst_type;
        // val_params から単位(°C)や色を取得する設定
        this.params = JSON.parse(conf.val_params || '{}');
    }

    initUI() {
        const content = document.getElementById(`content-${this.name}`);
        // センサー用の大きな数値表示エリアを作成
        content.innerHTML = `
            <div class="sensor-value">
                <span id="val-${this.name}">--</span>
                <small>${this.params.unit || ''}</small>
            </div>
        `;
    }

    update(unitData) {
        const valEl = document.getElementById(`val-${this.name}`);
        const disp = document.getElementById(`disp-${this.name}`);
        
        // 動作状態の更新
        disp.innerText = (unitData.val_status || "IDLE").toUpperCase();
        
        // 数値の更新 (unitData.env_temp などが入ってくる想定)
        // 汎用的にするために env_ プレフィックスの値を自動取得
        const value = unitData.env_value || unitData.env_temp || '--';
        valEl.innerText = value;

        // 閾値チェックで色を変えるなどの遊び心もここに追加可能
    }
}