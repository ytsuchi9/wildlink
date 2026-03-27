/**
 * VstManager: WildLink Event Standard (WES) 2026 司令塔
 * 役割: プラグインの動的ロード、MQTTイベントの解析・分配、およびUIの統合管理
 */
class VstManager {
    constructor(nodeId) {
        this.nodeId = nodeId;
        this.units = {}; 
        this.loadedScripts = new Set(); 
        this.mqttClient = null;
        this.isMqttConnected = false;
    }

    async init() {
        try {
            // PHP経由でノードの全ユニット構成を取得
            const res = await fetch(`api/get_node_config.php?sys_id=${this.nodeId}`);
            const configs = await res.json();

            // 1. 各ユニットに必要なJSファイルを並列ロード
            await this.loadRequiredScripts(configs);

            // 2. 物理的なUIラック（枠組み）を生成
            this.renderRack(configs);

            // 3. MQTT接続 (リアルタイム通信の確立)
            this.setupMqtt();

            // 4. 定期ポーリング開始 (MQTT切断時のバックアップ & Vital統計用)
            this.startLoop();
        } catch (e) { 
            console.error("[VstManager] Init Error:", e); 
        }
    }

    setupMqtt() {
        const brokerHost = window.location.hostname;
        const brokerPort = 9001; // WebSocket用ポート
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
                    console.log(`%c[VstManager] MQTT Active: ${this.nodeId}`, "color: #00ff00; font-weight: bold;");
                    
                    // WES 2026標準トピックを購読: nodes/{sys_id}/{role}/{type}
                    this.mqttClient.subscribe(`nodes/${this.nodeId}/#`);
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
     * トピック構造: nodes/{sys_id}/{role}/{type}
     * type: event (状態変化), env (生データ), status (定期報告)
     */
    dispatchMqtt(topic, payload) {
        try {
            const parts = topic.split('/');
            if (parts.length < 4) return;

            const role = parts[2];
            const type = parts[3];
            const data = JSON.parse(payload);
            
            // データにroleが含まれていない場合は補完
            if (!data.role) data.role = role;
            data.msg_type = type;

            const unit = this.units[role];
            if (unit && unit.instance) {
                // 各ユニットの onEvent または update メソッドへ飛ばす
                if (type === 'event' && typeof unit.instance.onEvent === 'function') {
                    unit.instance.onEvent(data);
                } else if (typeof unit.instance.update === 'function') {
                    // env や status は update で処理
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