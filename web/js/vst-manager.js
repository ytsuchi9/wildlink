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

    renderRack(configs) {
        const rack = document.getElementById('vst-rack');
        rack.innerHTML = '';
        configs.forEach(conf => {
            // 1. 共通の枠（シャーシ）を作成
            const div = document.createElement('div');
            div.id = `plugin-${conf.vst_type}`;
            div.className = `vst-plugin`;
            div.innerHTML = `
                <div class="plugin-header">
                    <span>${conf.vst_class}</span>
                    <span>${conf.vst_type.toUpperCase()}</span>
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
            } else {
                // 将来的に SensorUnit などが増える場所
                pluginInstance = { update: (data) => { console.log("Standard update", data); } };
            }

            // 3. 管理リストへ登録
            this.units[conf.vst_type] = {
                el: div,
                config: conf,
                instance: pluginInstance
            };

            // 4. プラグイン独自の初期描画（ボタン配置など）
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