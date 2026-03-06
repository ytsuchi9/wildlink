class CameraUnit {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        this.name = conf.vst_type;
    }

    // 初期UI構築（ボタンなど）
    initUI() {
        const ctrl = document.getElementById(`controls-${this.name}`);
        ctrl.innerHTML = `
            <button class="btn-control" onclick="CameraUnit.sendCmd('${this.name}', 'start')">STREAM START</button>
            <button class="btn-control" onclick="CameraUnit.sendCmd('${this.name}', 'stop')">STREAM STOP</button>
        `;
    }

    // 状態更新（マネージャーから毎周期呼ばれる）
    update(unitData) {
        const el = document.getElementById(`plugin-${this.name}`);
        const disp = document.getElementById(`disp-${this.name}`);
        const content = document.getElementById(`content-${this.name}`);
        
        const isStreaming = (unitData.val_status === 'streaming' || unitData.val_status === 'success');
        disp.innerText = (unitData.val_status || "IDLE").toUpperCase();

        if (isStreaming) {
            el.classList.add('u3'); // 3Uに拡張
            this.ensureStream(content);
        } else {
            el.classList.remove('u3'); // 1Uに戻す
            this.removeStream(content);
        }
    }

    ensureStream(container) {
        if (!document.getElementById(`view-${this.name}`)) {
            const img = document.createElement('img');
            img.id = `view-${this.name}`;
            img.src = `http://192.168.1.102:8080/stream/${this.name}?t=${Date.now()}`;
            img.style.width = "100%";
            container.prepend(img);
            document.getElementById(`disp-${this.name}`).style.fontSize = "0.7rem";
        }
    }

    removeStream(container) {
        const img = document.getElementById(`view-${this.name}`);
        if (img) img.remove();
        document.getElementById(`disp-${this.name}`).style.fontSize = "1.1rem";
    }

    // 静的メソッド：ボタンからのコマンド送信（追跡機能付き）
    static async sendCmd(target, action) {
        const btn = event.target;
        const originalText = btn.innerText;
        btn.disabled = true;
        btn.innerText = "SENDING...";

        try {
            const formData = new URLSearchParams();
            formData.append('node_id', NODE_ID);
            formData.append('cmd_type', 'vst_control');
            formData.append('cmd_json', JSON.stringify({ "action": action, "target": target }));

            const res = await fetch('send_cmd.php', { method: 'POST', body: formData });
            const data = await res.json();
            const cmdId = data.command_id;

            // ステータス追跡
            const track = async () => {
                const check = await fetch(`get_command_status.php?id=${cmdId}`);
                const status = await check.json();
                
                if (status.val_status === 'success') {
                    btn.innerText = "SUCCESS";
                    btn.style.backgroundColor = "var(--success-color)";
                    // 成功したら即座にマネージャーをリフレッシュ
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