/**
 * VstManager: WildLink Event Standard (WES) 
 * 役割: プラグインの管理、描画、およびMQTTイベントの各ユニットへのDispatcher
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
            const res = await fetch(`get_node_config.php?sys_id=${this.nodeId}`);
            const configs = await res.json();

            // 1. JSファイルをロード
            await this.loadRequiredScripts(configs);

            // クラス登録待ち (念のため)
            await new Promise(resolve => setTimeout(resolve, 50)); 

            // 2. 描画開始
            this.renderRack(configs);

            // 3. MQTTのセットアップ (Mosquitto 2.0.18 WebSocket対応版)
            this.setupMqtt();

            // 4. 定期ポーリング開始 (バックアップとして維持)
            this.startLoop();
        } catch (e) { 
            console.error("[VstManager] Init Error:", e); 
        }
    }

    /**
     * MQTTブローカーへの接続セットアップ
     */
    setupMqtt() {
        const brokerHost = window.location.hostname;
        const brokerPort = 9001; // 先ほど成功したポート
        const clientId = `web_${this.nodeId}_${Math.random().toString(16).substr(2, 5)}`;

        try {
            // Mosquitto 2.x 以降のWS接続では path を "" (空) にするのが標準
            this.mqttClient = new Paho.MQTT.Client(brokerHost, brokerPort, "", clientId);

            // ハンドラ設定
            this.mqttClient.onConnectionLost = (res) => {
                this.isMqttConnected = false;
                if (res.errorCode !== 0) {
                    console.warn(`[VstManager] MQTT Connection Lost: ${res.errorMessage}`);
                    // 5秒後に再接続を試みる
                    setTimeout(() => this.setupMqtt(), 5000); 
                }
            };

            this.mqttClient.onMessageArrived = (message) => {
                this.dispatchMqttEvent(message.destinationName, message.payloadString);
            };

            // 接続オプション
            const options = {
                timeout: 3,
                onSuccess: () => {
                    this.isMqttConnected = true;
                    console.log(`%c[VstManager] MQTT Connected to ${brokerHost}:${brokerPort}`, "color: #00ff00; font-weight: bold;");
                    
                    // トピック購読 (WES標準)
                    this.mqttClient.subscribe("_local/#");
                    this.mqttClient.subscribe(`nodes/${this.nodeId}/#`);
                },
                onFailure: (err) => {
                    console.error("[VstManager] MQTT Connection Failed:", err);
                    setTimeout(() => this.setupMqtt(), 10000);
                },
                useSSL: false,
                mqttVersion: 4, // MQTT 3.1.1 
                cleanSession: true,
                keepAliveInterval: 60
            };

            this.mqttClient.connect(options);

        } catch (e) {
            console.error("[VstManager] MQTT Setup Exception:", e);
        }
    }

    /**
     * MQTTメッセージを Unit インスタンスへ分配
     */
    dispatchMqttEvent(topic, payload) {
        try {
            const data = JSON.parse(payload);
            const targetRole = data.role; // WES標準: どの役割（cam_main等）宛か

            if (!targetRole) return;

            const unit = this.units[targetRole];
            if (unit && unit.instance && typeof unit.instance.onEvent === 'function') {
                console.debug(`[VstManager] Event [${data.event}] -> [${targetRole}]`);
                unit.instance.onEvent(data);
            }
        } catch (e) {
            // 非JSON形式のメッセージは無視
        }
    }

    async loadRequiredScripts(configs) {
        const loadPromises = [];
        configs.forEach(conf => {
            if (parseInt(conf.is_active) === 0) return;
            const scriptName = `${conf.vst_class.toLowerCase()}-unit.js`;
            const scriptPath = `js/plugins/${scriptName}`;

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
            script.onload = () => resolve();
            script.onerror = () => {
                console.error(`[VstManager] Script Load Error: ${path}`);
                resolve();
            };
            document.head.appendChild(script);
        });
    }

    renderRack(configs) {
        const rack = document.getElementById('vst-rack');
        if (!rack) return;
        rack.innerHTML = '';

        configs.forEach(conf => {
            if (parseInt(conf.is_active) === 0) return;

            const roleName = conf.vst_role_name;
            const displayName = conf.vst_description || roleName.toUpperCase();
            const hwInfo = conf.hw_bus_addr ? `(${conf.hw_bus_addr})` : '';
            
            const div = document.createElement('div');
            div.id = `plugin-${roleName}`;
            
            const isEnabled = (parseInt(conf.val_enabled) === 1);
            div.className = `vst-plugin ${isEnabled ? '' : 'unit-disabled'}`;
            
            div.innerHTML = `
                <div class="plugin-header">
                    <span title="Class: ${conf.vst_class}">${conf.vst_class}</span>
                    <span class="plugin-role">${displayName} <small>${hwInfo}</small></span>
                </div>
                <div class="plugin-content" id="content-${roleName}">
                    <div class="status-text" id="disp-${roleName}">
                        ${isEnabled ? 'INITIALIZING...' : 'DISABLED'}
                    </div>
                </div>
                <div class="vst-controls" id="controls-${roleName}"></div>
            `;
            rack.appendChild(div);

            let pluginInstance = null;
            if (isEnabled) {
                // クラス名の正規化 (例: camera -> CameraUnit)
                const className = conf.vst_class.charAt(0).toUpperCase() + conf.vst_class.slice(1).toLowerCase() + "Unit";
                const TargetClass = window[className];

                if (typeof TargetClass === 'function') {
                    try {
                        pluginInstance = new TargetClass(conf, this);
                    } catch (e) { console.error(`[VstManager] Instance Error [${roleName}]:`, e); }
                } else {
                    console.warn(`[VstManager] Class [${className}] not found.`);
                }
            }

            this.units[roleName] = { el: div, config: conf, instance: pluginInstance };

            if (pluginInstance && typeof pluginInstance.initUI === 'function') {
                pluginInstance.initUI();
            }
        });
    }

    startLoop() {
        this.refresh();
        setInterval(() => this.refresh(), 5000); // 負荷軽減のため5秒に延長
    }

    async refresh() {
        // MQTTが繋がっていない時のみ、あるいは Vital 情報取得のために継続
        try {
            const res = await fetch(`get_node_status.php?sys_id=${this.nodeId}`);
            const data = await res.json();
            
            // Vitals (CPU温度など) の更新
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

            // MQTTが死んでいる時のバックアップとして status 更新
            if (!this.isMqttConnected && data.roles) {
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
        } catch (e) { /* ignore */ }
    }
}