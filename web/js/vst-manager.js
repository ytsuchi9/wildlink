class VstManager {
    constructor(nodeId) {
        this.nodeId = nodeId;
        this.units = {}; 
        this.loadedScripts = new Set(); // 重複ロード防止用
    }

    async init() {
        try {
            const res = await fetch(`get_node_config.php?sys_id=${this.nodeId}`);
            const configs = await res.json();

            // 1. 必要なJSファイルを動的にロード
            await this.loadRequiredScripts(configs);

            // 💡 2. クラスが window に登録されるまでわずかに待機 & 存在確認
            // (非同期ロード直後は window に反映されるまでラグがあるため)
            await new Promise(resolve => setTimeout(resolve, 50)); 

            // 3. 描画開始
            this.renderRack(configs);
            this.startLoop();
        } catch (e) { 
            console.error("Manager Init Error:", e); 
        }
    }

    /**
     * DBの構成を見て、必要なプラグインJSを動的にロードする
     */
    async loadRequiredScripts(configs) {
        const loadPromises = [];

        configs.forEach(conf => {
            if (parseInt(conf.is_active) === 0) return;

            // クラス名(Camera等)からファイル名を生成 (js/plugins/camera-unit.js)
            const scriptName = `${conf.vst_class.toLowerCase()}-unit.js`;
            const scriptPath = `js/plugins/${scriptName}`;

            if (!this.loadedScripts.has(scriptPath)) {
                loadPromises.push(this.injectScript(scriptPath));
                this.loadedScripts.add(scriptPath);
            }
        });

        return Promise.all(loadPromises);
    }

    /**
     * scriptタグをDOMに注入し、ロード完了を待機するPromise
     */
    injectScript(path) {
        return new Promise((resolve) => {
            const script = document.createElement('script');
            script.src = path;
            script.onload = () => {
                console.log(`[VstManager] Plugin loaded: ${path}`);
                resolve();
            };
            script.onerror = () => {
                console.warn(`[VstManager] Plugin failed to load: ${path}`);
                resolve(); // 失敗しても全体の初期化は止めない
            };
            document.head.appendChild(script);
        });
    }

    renderRack(configs) {
        const rack = document.getElementById('vst-rack');
        if (!rack) return;
        rack.innerHTML = '';

        configs.forEach(conf => {
            // DB管理上で無効（is_active=0）なら、枠すら作らずスキップ
            if (parseInt(conf.is_active) === 0) return;

            const roleName = conf.vst_role_name;
            const displayName = conf.vst_description || roleName.toUpperCase();
            const hwInfo = conf.hw_bus_addr ? `(${conf.hw_bus_addr})` : '';
            
            // 1. 共通の枠（シャーシ）を作成
            const div = document.createElement('div');
            div.id = `plugin-${roleName}`;
            
            // val_enabled が 0 なら 'unit-disabled' クラスを付与してグレーアウト
            const isEnabled = (parseInt(conf.val_enabled) === 1);
            const enabledClass = isEnabled ? '' : 'unit-disabled';
            div.className = `vst-plugin ${enabledClass}`;
            
            div.innerHTML = `
                <div class="plugin-header">
                    <span title="Type: ${conf.vst_type}">${conf.vst_class}</span>
                    <span class="plugin-role">${displayName} <small>${hwInfo}</small></span>
                </div>
                <div class="plugin-content" id="content-${roleName}">
                    <div class="status-text" id="disp-${roleName}">
                        ${isEnabled ? 'OFFLINE' : 'DISABLED'}
                    </div>
                </div>
                <div class="vst-controls" id="controls-${roleName}"></div>
            `;
            rack.appendChild(div);

            // 2. インスタンス生成
            let pluginInstance = null;
            if (isEnabled) {
                // vst_class (Camera, Sensor, Switch) からクラス名を生成
                const className = `${conf.vst_class}Unit`;
                const TargetClass = window[className];

                if (typeof TargetClass === 'function') {
                    try {
                        pluginInstance = new TargetClass(conf, this);
                        console.log(`[VstManager] Successfully instantiated ${className} for [${roleName}]`);
                    } catch (e) {
                        console.error(`[VstManager] Failed to create instance of ${className} for ${roleName}:`, e);
                    }
                } else {
                    // ここでエラーが出る場合は、JSファイルのロード順か、windowへの登録漏れです
                    console.error(`[VstManager] Class [${className}] not found in window object. Check if ${conf.vst_class.toLowerCase()}-unit.js is loaded correctly.`);
                }
            }

            // 3. 管理リストへ登録
            this.units[roleName] = {
                el: div,
                config: conf,
                instance: pluginInstance
            };

            // 4. 初期描画 (ボタンの配置など)
            if (pluginInstance && typeof pluginInstance.initUI === 'function') {
                try {
                    pluginInstance.initUI();
                } catch (e) {
                    console.error(`[VstManager] Error during initUI for ${roleName}:`, e);
                }
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

            if (data.roles && Array.isArray(data.roles)) {
                data.roles.forEach(statusInfo => {
                    const rName = statusInfo.vst_role_name;
                    const unit = this.units[rName];
                    if (unit && unit.instance && parseInt(unit.config.val_enabled) === 1) {
                        unit.instance.update({
                            val_status: statusInfo.val_status || 'offline',
                            env: data.env_latest ? data.env_latest.val_data : {} 
                        });
                    }
                });
            }
        } catch (e) { console.error("Refresh Error:", e); }
    }
}