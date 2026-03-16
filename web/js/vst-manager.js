class VstManager {
    constructor(nodeId) {
        this.nodeId = nodeId;
        this.units = {}; // ユニット名(vst_type)をキーにしたオブジェクト
    }

    async init() {
        try {
            const res = await fetch(`get_node_config.php?sys_id=${this.nodeId}`);
            const configs = await res.json();
            this.renderRack(configs);
            this.startLoop();
        } catch (e) { console.error("Manager Init Error:", e); }
    }

    // renderRack メソッドのみ抜粋・修正
    renderRack(configs) {
        const rack = document.getElementById('vst-rack');
        rack.innerHTML = '';
        configs.forEach(conf => {
            // --- 💡 修正箇所：PHPですでにデコード済みなので、存在確認だけでOK ---
            // もし PHP側がデコードに失敗して null を返していても、空のオブジェクトを代入して
            // CameraUnit 等の初期化でエラーが起きないようにガードします。
            conf.val_params = conf.val_params || {}; 
            conf.val_unit_map = conf.val_unit_map || {};
            // -----------------------------------------------------------
            
            // 表示名の決定：role_nameがあればそれを、なければ vst_type を大文字で使う
            const displayName = conf.vst_role_name || conf.vst_type.toUpperCase();
            // 物理接続情報 (18番ピン、0x40アドレスなど)
            const hwInfo = conf.hw_bus_addr ? `(${conf.hw_bus_addr})` : '';

            // 1. 共通の枠（シャーシ）を作成
            const div = document.createElement('div');
            div.id = `plugin-${conf.vst_type}`;
            div.className = `vst-plugin`;
            div.innerHTML = `
                <div class="plugin-header">
                    <span title="${conf.vst_description || ''}">${conf.vst_class}</span>
                    <span class="plugin-role">${displayName} <small>${hwInfo}</small></span>
                </div>
                <div class="plugin-content" id="content-${conf.vst_type}">
                    <div class="status-text" id="disp-${conf.vst_type}">OFFLINE</div>
                </div>
                <div class="vst-controls" id="controls-${conf.vst_type}"></div>
            `;
            rack.appendChild(div);

            // 2. ui_component_type に応じてプラグインクラスを割り当て
            let pluginInstance = null;
            if (conf.ui_component_type === 'camera') {
                pluginInstance = new CameraUnit(conf, this);
            } else if (conf.ui_component_type === 'sensor') {
                // 今後追加する汎用センサーユニット（仮）
                // pluginInstance = new SensorUnit(conf, this);
                pluginInstance = { update: (data) => { console.log("Sensor update", data); } };
            } else {
                pluginInstance = { update: (data) => { console.log("Standard update", data); } };
            }

            // 3. 管理リストへ登録
            this.units[conf.vst_type] = {
                el: div,
                config: conf,
                instance: pluginInstance
            };

            // 4. プラグイン独自の初期描画
            if (pluginInstance.initUI) pluginInstance.initUI();
        });
    }

    startLoop() {
        this.refresh();
        setInterval(() => this.refresh(), 3000);
    }

    async refresh() {
        try {
            // 1. sys_id でリクエスト
            const res = await fetch(`get_node_status.php?sys_id=${this.nodeId}`);
            const data = await res.json();
            
            // 2. バイタルの更新（データがある時だけ実行）
            if (data.vitals) {
                const v = data.vitals;
                if(document.getElementById('vital-cpu')) document.getElementById('vital-cpu').innerText = v.sys_cpu_t || '--';
                if(document.getElementById('vital-rssi')) document.getElementById('vital-rssi').innerText = v.net_rssi || '--';
                if(document.getElementById('vital-up')) document.getElementById('vital-up').innerText = v.sys_up || '--';
                if(document.getElementById('vital-time')) document.getElementById('vital-time').innerText = v.last_seen || '--:--:--';
            }

            // 3. ユニット状態の更新
            // unit_statuses があればそれを使う、なければ全体の sys_status で代用
            const statuses = data.unit_statuses || {};
            
            Object.keys(this.units).forEach(name => {
                const unit = this.units[name];
                // 個別のステータスがあればそれを、なければ全体の sys_status を採用
                const currentStatus = statuses[name] || data.sys_status || 'offline';
                
                const payload = {
                    val_status: currentStatus,
                    env: data.env_data || {} // もし環境数値があれば
                };
                
                // ここで各プラグイン（CameraUnitなど）の update を呼ぶ
                if (unit.instance && typeof unit.instance.update === 'function') {
                    unit.instance.update(payload);
                }
            });

        } catch (e) { 
            console.error("Refresh Error:", e);
            // エラーが起きてもループを止めないためにあえて何もしない
        }
    }
}