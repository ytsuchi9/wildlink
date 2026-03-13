class VstManager {
    constructor(nodeId) {
        this.nodeId = nodeId;
        this.units = {}; // ユニット名(vst_type)をキーにしたオブジェクト
    }

    async init() {
        try {
            const res = await fetch(`get_node_config.php?node_id=${this.nodeId}`);
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
            const res = await fetch(`get_node_status.php?node_id=${this.nodeId}`);
            const data = await res.json();
            
            // 1. バイタル更新（マネージャーが直接担当）
            if (data.vitals) {
                document.getElementById('vital-cpu').innerText = data.vitals.sys_cpu_t || '--';
                document.getElementById('vital-rssi').innerText = data.vitals.net_rssi || '--';
                document.getElementById('vital-time').innerText = data.server_time || '--:--:--';
            }

            // 2. プラグインへの通知
            if (data.unit_statuses) {
                for (const [name, status] of Object.entries(data.unit_statuses)) {
                    if (this.units[name] && this.units[name].instance) {
                        
                        // そのユニットに関連する環境データがあれば一緒に渡してあげる
                        // 例えば cam_main のパケットの中に env_lux 等が含まれている可能性を考慮
                        const payload = {
                            val_status: status,
                            env: data.env_data // センサーデータ一式を丸ごと渡す
                        };

                        // 各プラグイン（CameraUnit, SensorUnit等）のupdateを叩く
                        this.units[name].instance.update(payload);
                    }
                }
            }
        } catch (e) { console.error("Refresh Error:", e); }
    }
}