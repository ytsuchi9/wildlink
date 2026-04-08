/**
 * VstManager: WES 2026 対応版
 */
class VstManager {
    // 🌟 groupId を追加。PHP側から渡すか、global変数を参照するようにします。
    constructor(nodeId, groupId = "home_internal") {
        this.nodeId = nodeId;
        this.groupId = groupId; // 🌟 追加
        this.units = {}; 
        this.loadedScripts = new Set(); 
        this.mqttClient = null;
        this.isMqttConnected = false;
    }

    async init() {
        try {
            const res = await fetch(`api/get_node_config.php?sys_id=${this.nodeId}`);
            const configs = await res.json();

            await this.loadRequiredScripts(configs);
            this.renderRack(configs);
            this.setupMqtt();
            this.startLoop();
        } catch (e) { 
            console.error("[VstManager] Init Error:", e); 
        }
    }

    setupMqtt() {
        const brokerHost = window.location.hostname;
        const brokerPort = 9001; 
        const clientId = `web_${this.nodeId}_${Math.random().toString(16).substr(2, 5)}`;

        try {
            this.mqttClient = new Paho.MQTT.Client(brokerHost, brokerPort, "", clientId);

            this.mqttClient.onConnectionLost = (res) => {
                this.isMqttConnected = false;
                if (res.errorCode !== 0) {
                    console.warn(`[VstManager] MQTT Connection Lost: ${res.errorMessage}`);
                    setTimeout(() => this.setupMqtt(), 5000); 
                }
            };

            this.mqttClient.onMessageArrived = (message) => {
                this.dispatchMqtt(message.destinationName, message.payloadString);
            };

            const options = {
                timeout: 3,
                onSuccess: () => {
                    this.isMqttConnected = true;
                    console.log(`%c[VstManager] MQTT Active: ${this.nodeId} (Group: ${this.groupId})`, "color: #00ff00; font-weight: bold;");
                    
                    // 🌟 修正: WES 2026標準トピックを購読
                    // 形式: wildlink/{groupId}/{nodeId}/#
                    const topic = `wildlink/${this.groupId}/${this.nodeId}/#`;
                    this.mqttClient.subscribe(topic);
                    console.log(`[VstManager] Subscribed to: ${topic}`);
                },
                onFailure: (err) => {
                    console.error("[VstManager] MQTT Connection Failed:", err);
                    setTimeout(() => this.setupMqtt(), 10000);
                },
                useSSL: (window.location.protocol === "https:"),
                mqttVersion: 4,
                cleanSession: true
            };

            this.mqttClient.connect(options);
        } catch (e) {
            console.error("[VstManager] MQTT Setup Exception:", e);
        }
    }

    /**
     * 🌟 修正: 階層構造の変化に対応
     * Topic index: 0:wildlink / 1:group / 2:node / 3:role / 4:type
     */
    dispatchMqtt(topic, payload) {
        try {
            const parts = topic.split('/');
            if (parts.length < 5) return; // wildlink/group/node/role/type なので最低5つ

            const role = parts[3]; // 🌟 2 から 3 へ変更
            const type = parts[4]; // 🌟 3 から 4 へ変更
            const data = JSON.parse(payload);
            
            if (!data.role) data.role = role;
            data.msg_type = type;

            const unit = this.units[role];
            if (unit && unit.instance) {
                // event タイプかつ onEvent 実装済みならキック
                if (type === 'event' && typeof unit.instance.onEvent === 'function') {
                    unit.instance.onEvent(data);
                } else if (typeof unit.instance.update === 'function') {
                    unit.instance.update(data);
                }
            }
        } catch (e) {
            console.warn("[VstManager] Dispatch error:", e, topic, payload);
        }
    }

    async loadRequiredScripts(configs) {
        const loadPromises = [];
        configs.forEach(conf => {
            if (parseInt(conf.is_active) === 0) return;
            const scriptPath = `js/plugins/${conf.vst_class.toLowerCase()}-unit.js`;
            if (!this.loadedScripts.has(scriptPath)) {
                loadPromises.push(this.injectScript(scriptPath));
                this.loadedScripts.add(scriptPath);
            }
        });
        return Promise.all(loadPromises);
    }

    injectScript(path) {
        return new Promise((resolve) => {
            const script = document.createElement('script');
            script.src = path;
            script.onload = resolve;
            script.onerror = () => { console.error(`Failed to load: ${path}`); resolve(); };
            document.head.appendChild(script);
        });
    }

    renderRack(configs) {
        const rack = document.getElementById('vst-rack');
        if (!rack) return;
        rack.innerHTML = '';

        configs.forEach(conf => {
            if (parseInt(conf.is_active) === 0) return;

            const role = conf.vst_role_name;
            const div = document.createElement('div');
            div.id = `plugin-${role}`;
            
            const isEnabled = (parseInt(conf.val_enabled) === 1);
            div.className = `vst-plugin ${isEnabled ? '' : 'unit-disabled'}`;
            
            div.innerHTML = `
                <div class="plugin-header">
                    <span class="badge-class">${conf.vst_class.toUpperCase()}</span>
                    <span class="plugin-role">${conf.vst_description || role}</span>
                </div>
                <div class="plugin-content" id="content-${role}">
                    <div class="status-text" id="disp-${role}">INITIALIZING...</div>
                </div>
                <div class="vst-controls" id="controls-${role}"></div>
            `;
            rack.appendChild(div);

            // インスタンス化 (例: logger -> LoggerUnit)
            const className = conf.vst_class.charAt(0).toUpperCase() + conf.vst_class.slice(1).toLowerCase() + "Unit";
            const TargetClass = window[className];

            if (typeof TargetClass === 'function') {
                const instance = new TargetClass(conf, this);
                this.units[role] = { el: div, config: conf, instance: instance };
                if (instance.initUI) instance.initUI();
            }
        });
    }

    startLoop() {
        this.refresh();
        setInterval(() => this.refresh(), 5000);
    }

    async refresh() {
        try {
            const res = await fetch(`api/get_node_status.php?sys_id=${this.nodeId}`);
            const data = await res.json();
            
            // Vitals更新
            if (data.vitals) {
                const v = data.vitals;
                const setV = (id, val) => { const el = document.getElementById(id); if (el) el.innerText = val || '--'; };
                setV('vital-cpu', `${v.sys_cpu_t}°C`);
                setV('vital-rssi', `${v.net_rssi} dBm`);
                setV('vital-up', v.sys_up);
            }

            // 各ユニットへの同期 (MQTT未接続時の保険)
            if (data.roles) {
                data.roles.forEach(s => {
                    const unit = this.units[s.vst_role_name];
                    if (unit && unit.instance && !this.isMqttConnected) {
                        unit.instance.update(s);
                    }
                });
            }
        } catch (e) { /* silent */ }
    }
}