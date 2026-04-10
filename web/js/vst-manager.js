/**
 * VstManager: WES 2026 対応版
 */
class VstManager {
    // 🌟 groupId を追加。PHP側から渡すか、global変数を参照するようにします。
    // 🌟 prefix を引数に追加し、デフォルト値を設定
    
    // 🌟 プラグインを保持するための静的な保管場所
    static plugins = {};

    // 🌟 プラグインを登録するためのメソッド（これが足りなかった！）
    static registerPlugin(roleType, pluginClass) {
        this.plugins[roleType.toLowerCase()] = pluginClass;
        console.log(`[VstManager] Plugin registered: ${roleType}`);
    }

    constructor(nodeId, groupId = "home_internal", prefix = "wildlink") {
        this.nodeId = nodeId;
        this.groupId = groupId;
        this.prefix = prefix; // 🌟 追加
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
                
                    // 🌟 修正: WES 2026標準トピックを購読
                    // 🌟 ハードコードを排除し、動的なトピックを生成
                    const topic = `${this.prefix}/${this.groupId}/${this.nodeId}/#`;
                    this.mqttClient.subscribe(topic);
                    console.log(`%c[VstManager] MQTT Active: ${topic}`, "color: #00ff00; font-weight: bold;");
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
            if (parts.length < 5) return;

            const role = parts[3];
            const type = parts[4];
            
            // --- 💡 超堅牢なJSON解析 ---
            let data = payload;
            // payloadが文字列である限り、パースし続ける（二重シリアライズ対策）
            while (typeof data === 'string') {
                try {
                    data = JSON.parse(data);
                } catch (e) {
                    // JSONではない文字列（またはパース失敗）ならループを抜ける
                    break; 
                }
            }

            // dataがオブジェクトでなければ配送不能として終了
            if (!data || typeof data !== 'object') {
                console.warn("[VstManager] Invalid data format:", data);
                return;
            }

            // 🌟 ここで確実にオブジェクトに対してプロパティをセット
            data.role = role;
            data.msg_type = type;

            const unit = this.units[role];
            if (unit && unit.instance) {
                if (type === 'event' && typeof unit.instance.onEvent === 'function') {
                    unit.instance.onEvent(data);
                } else if (typeof unit.instance.update === 'function') {
                    unit.instance.update(data);
                }
            }
        } catch (e) {
            console.error("[VstManager] Dispatch critical error:", e);
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

    /**
     * データベースの設定に基づき、ラックにユニットを配置・初期化する
     * @param {Array} configs - api/get_node_config.php から取得した設定配列
     */
    renderRack(configs) {
        const rack = document.getElementById('vst-rack');
        if (!rack) return;
        rack.innerHTML = ''; // 既存の表示をクリア

        configs.forEach(conf => {
            // 1. 無効なユニット（is_active=0）はスキップ
            if (parseInt(conf.is_active) === 0) return;

            const role = conf.vst_role_name; // 'cam_main', 'sns_move' など
            const vstClass = conf.vst_class.toLowerCase(); // 'camera', 'system' など
            
            // 2. ユニットの外装（DOMエレメント）を作成
            const div = document.createElement('div');
            div.id = `plugin-${role}`;
            
            // 有効・無効（val_enabled）に応じてCSSクラスを付与
            const isEnabled = (parseInt(conf.val_enabled) === 1);
            div.className = `vst-plugin ${isEnabled ? '' : 'unit-disabled'}`;
            
            // 共通のHTML構造を流し込む
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

            // 3. プログラム（クラス）の特定
            // [優先順位1] VstManager.registerPlugin で登録されたクラス
            let TargetClass = VstManager.plugins[vstClass];
            
            // [優先順位2] 登録がない場合、命名規則（例: CameraUnit）から window オブジェクト内を探す
            if (!TargetClass) {
                const className = conf.vst_class.charAt(0).toUpperCase() + conf.vst_class.slice(1).toLowerCase() + "Unit";
                TargetClass = window[className];
            }

            // 4. インスタンス化と初期化
            if (typeof TargetClass === 'function') {
                // クラスから実体（インスタンス）を作成し、設定値とマネージャー自身(this)を渡す
                const instance = new TargetClass(conf, this);
                
                // マネージャー内で管理するために保持
                this.units[role] = { 
                    el: div, 
                    config: conf, 
                    instance: instance 
                };

                // ユニット固有のUI初期化（ボタンのイベント登録など）を実行
                if (typeof instance.initUI === 'function') {
                    instance.initUI();
                }
            } else {
                console.warn(`[VstManager] 対応するプログラムが見つかりません: ${vstClass}`);
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