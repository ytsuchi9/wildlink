class VstManager {
    constructor(nodeId) {
        this.nodeId = nodeId;
        this.units = {}; // キーを vst_role_name に変更！
    }

    async init() {
        try {
            const res = await fetch(`get_node_config.php?sys_id=${this.nodeId}`);
            const configs = await res.json();
            this.renderRack(configs);
            this.startLoop();
        } catch (e) { console.error("Manager Init Error:", e); }
    }

    renderRack(configs) {
        const rack = document.getElementById('vst-rack');
        if (!rack) return;
        rack.innerHTML = '';

        configs.forEach(conf => {
            // PHP側でデコード済みだが、念のためのガード
            conf.val_params = conf.val_params || {}; 
            conf.val_unit_map = conf.val_unit_map || {};
            
            // 2026年仕様：一意の識別子として role_name を使用
            const roleName = conf.vst_role_name || conf.vst_type;
            const displayName = conf.vst_role_name || conf.vst_type.toUpperCase();
            const hwInfo = conf.hw_bus_addr ? `(${conf.hw_bus_addr})` : '';

            // 1. 共通の枠（シャーシ）を作成
            const div = document.createElement('div');
            // IDも roleName ベースに変更して重複を避ける
            div.id = `plugin-${roleName}`;
            div.className = `vst-plugin`;
            div.innerHTML = `
                <div class="plugin-header">
                    <span title="${conf.vst_description || ''}">${conf.vst_class}</span>
                    <span class="plugin-role">${displayName} <small>${hwInfo}</small></span>
                </div>
                <div class="plugin-content" id="content-${roleName}">
                    <div class="status-text" id="disp-${roleName}">OFFLINE</div>
                </div>
                <div class="vst-controls" id="controls-${roleName}"></div>
            `;
            rack.appendChild(div);

            // 2. ui_component_type に応じてインスタンス生成
            let pluginInstance = null;
            if (conf.ui_component_type === 'camera') {
                pluginInstance = new CameraUnit(conf, this);
            } else if (conf.ui_component_type === 'sensor') {
                // 将来の SensorUnit 用
                pluginInstance = new SensorUnit(conf, this);
            } else {
                // デフォルトの簡易表示
                pluginInstance = { 
                    update: (data) => { 
                        const d = document.getElementById(`disp-${roleName}`);
                        if(d) d.innerText = data.val_status.toUpperCase();
                    } 
                };
            }

            // 3. 管理リストへ登録（キーを roleName に）
            this.units[roleName] = {
                el: div,
                config: conf,
                instance: pluginInstance
            };

            // 4. プラグイン独自の初期描画
            if (pluginInstance && typeof pluginInstance.initUI === 'function') {
                pluginInstance.initUI();
            }
        });
    }

    startLoop() {
        this.refresh();
        setInterval(() => this.refresh(), 3000);
    }

    async refresh() {
        try {
            const res = await fetch(`get_node_status.php?sys_id=${this.nodeId}`);
            const data = await res.json();
            
            // 2. バイタルの更新（get_node_status.php の新しいキー構造に対応）
            if (data.vitals) {
                const v = data.vitals;
                const updateVital = (id, val) => {
                    const el = document.getElementById(id);
                    if (el) el.innerText = val || '--';
                };
                updateVital('vital-cpu', v.sys_cpu_t);
                updateVital('vital-rssi', v.net_rssi);
                updateVital('vital-up', v.sys_up);
                updateVital('vital-time', v.last_seen);
            }

            // 3. ユニット状態の更新（roles 配列を回す）
            if (data.roles && Array.isArray(data.roles)) {
                data.roles.forEach(statusInfo => {
                    const rName = statusInfo.vst_role_name;
                    const unit = this.units[rName];
                    
                    if (unit && unit.instance) {
                        const payload = {
                            val_status: statusInfo.val_status || 'offline',
                            // node_data からの最新数値があれば渡す
                            env: data.env_latest ? data.env_latest.val_data : {} 
                        };
                        unit.instance.update(payload);
                    }
                });
            }

        } catch (e) { 
            console.error("Refresh Error:", e);
        }
    }
}