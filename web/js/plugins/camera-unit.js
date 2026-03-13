class CameraUnit {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        this.name = conf.vst_type;
        
        const params = conf.val_params || {};
        this.streamHost = params.host || window.location.hostname; 
        
        // 💡 修正: params.port ではなく params.net_port を参照
        // 💡 さらに MJPEG Bridge は 8080 で待ち受けているので、ここは 8080 固定が正解
        this.streamPort = "8080"; 
    }

    // 初期UI構築（ボタンなど）
    initUI() {
        const ctrl = document.getElementById(`controls-${this.name}`);
        ctrl.innerHTML = `
            <button class="btn-control" onclick="CameraUnit.sendCmd('${this.name}', 'start')">STREAM START</button>
            <button class="btn-control" onclick="CameraUnit.sendCmd('${this.name}', 'stop')">STREAM STOP</button>
        `;
    }

    // 状態更新
    update(unitData) {
        const el = document.getElementById(`plugin-${this.name}`);
        const disp = document.getElementById(`disp-${this.name}`);
        const content = document.getElementById(`content-${this.name}`);
        
        const isStreaming = (unitData.val_status === 'streaming' || unitData.val_status === 'success');
        disp.innerText = (unitData.val_status || "IDLE").toUpperCase();

        if (isStreaming) {
            el.classList.add('u3');
            this.ensureStream(content);
        } else {
            el.classList.remove('u3');
            this.removeStream(content);
        }
    }

    ensureStream(container) {
        let img = document.getElementById(`view-${this.name}`);
        
        if (!img) {
            img = document.createElement('img');
            img.id = `view-${this.name}`;
            img.style.width = "100%";
            
            // 💡 リトライロジック + 動的URL
            const buildUrl = () => `http://${this.streamHost}:${this.streamPort}/stream/${this.name}?t=${Date.now()}`;

            img.onerror = () => {
                console.warn(`[${this.name}] Stream load error. Retrying in 1.5s...`);
                setTimeout(() => {
                    // まだ要素がDOMに存在する場合のみリロード
                    const currentImg = document.getElementById(`view-${this.name}`);
                    if (currentImg) currentImg.src = buildUrl();
                }, 1500); 
            };

            img.src = buildUrl();
            container.prepend(img);
            document.getElementById(`disp-${this.name}`).style.fontSize = "0.7rem";
        }
    }

    removeStream(container) {
        const img = document.getElementById(`view-${this.name}`);
        if (img) {
            // 💡 削除する前にsrcを空にするのがコツ
            // これにより、ブラウザが「このストリーム通信はもう不要だ」と判断し、
            // wmp_stream_rx.py 側に切断（GeneratorExit）を発生させやすくなります。
            img.src = ""; 
            img.remove();
            console.log(`[${this.name}] Stream stopped and element removed.`);
        }
        document.getElementById(`disp-${this.name}`).style.fontSize = "1.1rem";
    }

    // static sendCmd 内の NODE_ID は camviewer.html で定義されているグローバル変数を使用
    static async sendCmd(target, action) {
        const btn = event.target;
        const originalText = btn.innerText;
        btn.disabled = true;
        btn.innerText = "SENDING...";

        try {
            const formData = new URLSearchParams();
            formData.append('node_id', NODE_ID); 
            formData.append('cmd_type', 'vst_control');

            // 💡 修正：統一基準に基づき "action": "start" ではなく "act_run": true を送る
            const cmdData = { 
                "target": target,
                "act_run": (action === 'start') // startならtrue, stopならfalse
            };
            formData.append('cmd_json', JSON.stringify(cmdData));

            const res = await fetch('send_cmd.php', { method: 'POST', body: formData });
            const data = await res.json();
            const cmdId = data.command_id;

            const track = async () => {
                const check = await fetch(`get_command_status.php?id=${cmdId}`);
                const status = await check.json();
                
                if (status.val_status === 'success') {
                    btn.innerText = "SUCCESS";
                    btn.style.backgroundColor = "var(--success-color)";
                    if (window.vstManagerInstance) window.vstManagerInstance.refresh();
                    setTimeout(() => CameraUnit.resetBtn(btn, originalText), 2000);
                } else if (status.val_status === 'error') {
                    btn.innerText = "ERROR";
                    btn.style.backgroundColor = "var(--error-color)";
                    setTimeout(() => CameraUnit.resetBtn(btn, originalText), 2000);
                } else {
                    setTimeout(track, 1000);
                }
            };
            track();
        } catch (e) { 
            console.error(e); 
            CameraUnit.resetBtn(btn, originalText);
        }
    }

    static resetBtn(btn, text) {
        btn.innerText = text;
        btn.disabled = false;
        btn.style.backgroundColor = "";
    }
}