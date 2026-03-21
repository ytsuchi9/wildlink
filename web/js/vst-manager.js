/**
 * VstManager: WildLink Event Standard (WES) 対応版
 * 役割: プラグインのロード、描画管理、およびMQTTイベントの各ユニットへの振り分け（Dispatcher）
 */
class VstManager {
    constructor(nodeId) {
        this.nodeId = nodeId;
        this.units = {}; 
        this.loadedScripts = new Set(); 
        this.mqttClient = null;
    }

    async init() {
        try {
            const res = await fetch(`get_node_config.php?sys_id=${this.nodeId}`);
            const configs = await res.json();

            // 1. 必要なJSファイルを動的にロード
            await this.loadRequiredScripts(configs);

            // クラス登録待ち
            await new Promise(resolve => setTimeout(resolve, 50)); 

            // 2. 描画開始
            this.renderRack(configs);

            // 💡 3. MQTTのセットアップ (WES標準化の核)
            this.setupMqtt();

            // 4. 定期ポーリング開始 (バックアップとして維持)
            this.startLoop();
        } catch (e) { 
            console.error("[VstManager] Init Error:", e); 
        }
    }

    /**
     * MQTTブローカーへの接続とイベントハンドリングのセットアップ
     */
    setupMqtt() {
        const brokerHost = window.location.hostname;
        const brokerPort = 9001; // WebSocket用ポート (websockify)
        const clientId = `web_client_${Math.random().toString(16).substr(2, 8)}`;

        try {
            // 💡 修正ポイント1: 第3引数を空文字列 "" にし、第4引数に clientId を渡す
            // Paho.MQTT.Client(host, port, path, clientId)
            this.mqttClient = new Paho.MQTT.Client(brokerHost, brokerPort, "", clientId);

            // 接続が切れた時の処理
            this.mqttClient.onConnectionLost = (responseObject) => {
                if (responseObject.errorCode !== 0) {
                    console.warn(`[VstManager] MQTT Lost: ${responseObject.errorMessage}`);
                    setTimeout(() => this.setupMqtt(), 5000); 
                }
            };

            // メッセージ受信時の振り分け
            this.mqttClient.onMessageArrived = (message) => {
                this.dispatchMqttEvent(message.destinationName, message.payloadString);
            };

            // 💡 修正ポイント2: connectオプションの最適化
            this.mqttClient.connect({
                onSuccess: () => {
                    console.log("[VstManager] MQTT Connected.");
                    // トピック購読
                    this.mqttClient.subscribe("_local/#");
                    this.mqttClient.subscribe(`nodes/${this.nodeId}/#`);
                },
                onFailure: (e) => {
                    console.error("[VstManager] MQTT Connect Failed:", e);
                },
                useSSL: false,
                keepAliveInterval: 30,
                mqttVersion: 4,      // 💡 MQTT 3.1.1 を強制
                cleanSession: true
            });
        } catch (e) {
            console.error("[VstManager] MQTT Setup Error:", e);
        }
    }

    /**
     * 受信したMQTTメッセージを適切なUnitインスタンスへ届ける
     */
    dispatchMqttEvent(topic, payload) {
        try {
            const data = JSON.parse(payload);
            const targetRole = data.role;

            if (!targetRole) return;

            // 担当ユニットを特定してイベントを丸投げ
            const unit = this.units[targetRole];
            if (unit && unit.instance && typeof unit.instance.onEvent === 'function') {
                console.log(`[VstManager] Dispatching event [${data.event}] to [${targetRole}]`);
                unit.instance.onEvent(data);
            }
        } catch (e) {
            console.warn("[VstManager] Failed to dispatch MQTT event. Payload might not be JSON.", e);
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
            script.onerror = () => resolve();
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

            let pluginInstance = null;
            if (isEnabled) {
                // クラス名の正規化 (頭文字大文字)
                const className = conf.vst_class.charAt(0).toUpperCase() + conf.vst_class.slice(1).toLowerCase() + "Unit";
                const TargetClass = window[className];

                if (typeof TargetClass === 'function') {
                    try {
                        pluginInstance = new TargetClass(conf, this);
                    } catch (e) { console.error(e); }
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
        } catch (e) { /* silent fail */ }
    }
}