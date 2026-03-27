/**
 * LoggerUnit: WES 2026 対応版
 * 役割: システムログやアプリログの収集指示と、受信したログの表示
 */
class LoggerUnit {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        this.name = conf.vst_role_name;
        this.maxLines = 50; // 画面に保持する最大行数
    }

    initUI() {
        const ctrl = document.getElementById(`controls-${this.name}`);
        const content = document.getElementById(`content-${this.name}`);
        if (!ctrl || !content) return;

        // ログ表示エリアの作成
        content.innerHTML = `
            <div id="log-display-${this.name}" class="log-viewer-area">
                <div class="log-placeholder">Waiting for logs...</div>
            </div>
        `;

        // 操作ボタン
        ctrl.innerHTML = `
            <div class="btn-group w-100">
                <button class="btn btn-sm btn-outline-info btn-fetch">FETCH LOGS</button>
                <button class="btn btn-sm btn-outline-danger btn-clear">CLEAR</button>
            </div>
        `;

        ctrl.querySelector('.btn-fetch').onclick = () => this.fetchLogs();
        ctrl.querySelector('.btn-clear').onclick = () => this.clearLogs();
    }

    /**
     * WESイベント処理: log_collection_started / finished 等
     */
    onEvent(data) {
        const disp = document.getElementById(`disp-${this.name}`);
        if (!disp) return;

        if (data.event === 'log_collection_started') {
            disp.innerText = "FETCHING...";
            disp.style.color = "#0dcaf0";
        } else if (data.event === 'log_collection_finished') {
            disp.innerText = "IDLE";
            disp.style.color = "";
        }
    }

    /**
     * データ更新処理: 'env' トピックから届くログ本文を処理
     */
    update(data) {
        // data.msg_type === 'env' の場合にログ本文が含まれる想定
        if (data.log_ext) {
            this.appendLog(data.log_ext);
        }
        
        // 通常のステータス表示更新
        const disp = document.getElementById(`disp-${this.name}`);
        if (disp && data.val_status) {
            disp.innerText = data.val_status.toUpperCase();
        }
    }

    appendLog(text) {
        const viewer = document.getElementById(`log-display-${this.name}`);
        if (!viewer) return;

        // プレースホルダーを削除
        const placeholder = viewer.querySelector('.log-placeholder');
        if (placeholder) placeholder.remove();

        const pre = document.createElement('pre');
        pre.className = 'log-entry';
        pre.innerText = `[${new Date().toLocaleTimeString()}]\n${text}`;

        viewer.prepend(pre); // 最新を上に

        // 行数制限
        while (viewer.children.length > this.maxLines) {
            viewer.lastChild.remove();
        }
    }

    clearLogs() {
        const viewer = document.getElementById(`log-display-${this.name}`);
        if (viewer) viewer.innerHTML = '<div class="log-placeholder">Cleared.</div>';
    }

    /**
     * Nodeへログ収集コマンドを送信 (act_run=True)
     */
    async fetchLogs() {
        const btn = document.querySelector(`#controls-${this.name} .btn-fetch`);
        btn.disabled = true;

        try {
            const formData = new URLSearchParams();
            formData.append('sys_id', this.manager.nodeId);
            formData.append('cmd_type', 'vst_control');
            formData.append('cmd_json', JSON.stringify({
                "role": this.name,
                "act_run": true
            }));

            await fetch('api/send_cmd.php', { method: 'POST', body: formData });
            // 結果はMQTT(onEvent)経由で戻ってくるので、ここでは待機しない
        } catch (e) {
            console.error("Fetch logs failed:", e);
        } finally {
            setTimeout(() => { btn.disabled = false; }, 2000);
        }
    }
}

window.LoggerUnit = LoggerUnit;