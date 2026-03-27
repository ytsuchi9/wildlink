<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>WildLink 2026 | System Monitor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.0/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <style>
        body { background-color: #f0f3f7; font-family: 'Segoe UI', Arial, sans-serif; color: #333; }
        .monitor-header { background: #fff; border-bottom: 1px solid #dee2e6; padding: 15px 0; margin-bottom: 25px; }
        .brand-title { font-family: 'Share Tech Mono', monospace; font-weight: bold; color: #1a1a1a; }
        
        /* ステータスカード */
        .card-node { border: none; border-radius: 12px; transition: transform 0.2s; box-shadow: 0 4px 15px rgba(0,0,0,0.05); text-decoration: none !important; color: inherit; display: block; }
        .card-node:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(0,0,0,0.1); }
        .status-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .online { background-color: #28a745; box-shadow: 0 0 8px #28a745; }
        .offline { background-color: #dc3545; }
        .vital-label { font-size: 0.7rem; color: #6c757d; text-transform: uppercase; letter-spacing: 0.5px; }
        .vital-value { font-family: 'Share Tech Mono', monospace; font-size: 1.1rem; }

        /* ロール（デバイス）バッジ */
        .role-badge { font-size: 0.65rem; padding: 2px 6px; border-radius: 4px; margin-right: 4px; background: #e9ecef; color: #495057; border: 1px solid #dee2e6; }
        .role-active { border-color: #28a745; color: #28a745; background: #f8fff9; }

        /* ログテーブル */
        .card-log { border: none; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden; }
        .log-table-container { max-height: 50vh; overflow-y: auto; background: white; }
        .log-table { font-size: 0.85rem; margin-bottom: 0; }
        .log-table thead { position: sticky; top: 0; background: #f8f9fa; z-index: 10; }
        
        .level-info { color: #0d6efd; }
        .level-warning { background-color: #fff3cd !important; }
        .level-error { background-color: #f8d7da !important; color: #721c24; }
        .badge-node { background-color: #495057; color: white; font-family: monospace; }
    </style>
</head>
<body>

<header class="monitor-header">
    <div class="container-fluid px-4">
        <div class="d-flex justify-content-between align-items-center">
            <h2 class="brand-title mb-0">🌿 WILDLINK 2026 <span class="fs-6 text-muted ms-2">SYSTEM MONITOR</span></h2>
            <div class="text-end">
                <div id="last-update" class="text-muted small">Initializing...</div>
                <div class="mt-1">
                    <button onclick="refreshAll()" class="btn btn-sm btn-outline-dark">Manual Refresh</button>
                </div>
            </div>
        </div>
    </div>
</header>

<div class="container-fluid px-4">
    <div id="node-cards" class="row mb-4">
        <div class="col-12 text-center py-5">
            <div class="spinner-border text-secondary" role="status"></div>
            <div class="mt-2 text-muted">Scanning Network...</div>
        </div>
    </div>

    <div class="card card-log">
        <div class="card-header bg-white py-3 d-flex justify-content-between align-items-center border-bottom">
            <h5 class="mb-0 fw-bold">Live System Logs</h5>
            <div>
                <span class="badge bg-secondary rounded-pill me-2" id="log-count">0 msgs</span>
                <button class="btn btn-sm btn-link text-decoration-none p-0" onclick="fetchLogs()">Reload Logs</button>
            </div>
        </div>
        <div class="log-table-container">
            <table class="table table-hover log-table">
                <thead>
                    <tr>
                        <th style="width: 160px;">Timestamp</th>
                        <th style="width: 100px;">Node</th>
                        <th style="width: 100px;">Type</th>
                        <th style="width: 80px;">LV</th>
                        <th>Message</th>
                        <th style="width: 80px;">Code</th>
                    </tr>
                </thead>
                <tbody id="log-body">
                    </tbody>
            </table>
        </div>
    </div>
</div>

<script>
    const CONFIG = {
        API_STATUS: 'api/get_node_status.php',
        API_LOGS: 'api/api_logs.php', // ログ取得用のAPIが別途必要
        REFRESH_INTERVAL: 5000
    };

    // --- 1. ノードステータスの取得と表示 ---
    async function fetchStatus() {
        try {
            // get_node_status.php は全ノードの状態を返す想定
            const response = await fetch(CONFIG.API_STATUS);
            if (!response.ok) throw new Error('Status API Error');
            const data = await response.json();
            
            const container = document.getElementById('node-cards');
            container.innerHTML = '';

            // data.nodes が存在する場合のループ処理
            const nodes = data.nodes || [];
            
            nodes.forEach(node => {
                const isOnline = node.is_online === true;
                const statusClass = isOnline ? 'online' : 'offline';
                
                // Role(デバイス)ごとの状態バッジを生成
                let rolesHtml = '';
                if (node.vst_states) {
                    node.vst_states.forEach(vst => {
                        const activeClass = vst.val_status === 'active' || vst.val_status === 'streaming' ? 'role-active' : '';
                        rolesHtml += `<span class="role-badge ${activeClass}">${vst.vst_role_name}</span>`;
                    });
                }

                const cardHtml = `
                    <div class="col-xl-3 col-md-4 col-sm-6 mb-4">
                        <a href="camviewer.html?sys_id=${node.sys_id}" class="card card-node p-3 h-100">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <div>
                                    <div class="vital-label">Node Identifier</div>
                                    <div class="fw-bold fs-5 text-primary">${node.sys_id}</div>
                                </div>
                                <span class="badge bg-light text-dark border small">${node.val_log_level || 'info'}</span>
                            </div>
                            
                            <div class="mb-3">
                                <span class="status-dot ${statusClass}"></span>
                                <span class="fw-bold small ${isOnline ? 'text-success' : 'text-danger'}">
                                    ${isOnline ? 'ONLINE' : 'OFFLINE'} 
                                    <span class="text-muted fw-normal">(${node.sys_status || 'unknown'})</span>
                                </span>
                            </div>

                            <div class="mb-3 d-flex flex-wrap gap-1">
                                ${rolesHtml || '<span class="text-muted small">No active roles</span>'}
                            </div>

                            <div class="row g-0 border-top pt-2">
                                <div class="col-6 border-end text-center">
                                    <div class="vital-label">CPU Temp</div>
                                    <div class="vital-value">${node.sys_cpu_temp ? parseFloat(node.sys_cpu_temp).toFixed(1) : '--'}<small class="fs-6">°C</small></div>
                                </div>
                                <div class="col-6 text-center">
                                    <div class="vital-label">Signal</div>
                                    <div class="vital-value">${node.net_rssi || '--'}<small class="fs-6 ps-1">dBm</small></div>
                                </div>
                            </div>
                            
                            <div class="mt-3 text-center border-top pt-2">
                                <small class="text-muted" style="font-size: 0.65rem;">
                                    Update: ${node.updated_at || '---'}
                                </small>
                            </div>
                        </a>
                    </div>
                `;
                container.innerHTML += cardHtml;
            });

            document.getElementById('last-update').innerText = `Last Update: ${new Date().toLocaleTimeString()}`;
        } catch (e) {
            console.error("Fetch Status Error:", e);
        }
    }

    // --- 2. ログの取得と表示 ---
    async function fetchLogs() {
        try {
            const response = await fetch(CONFIG.API_LOGS);
            if (!response.ok) return;
            const logs = await response.json();
            
            const tbody = document.getElementById('log-body');
            tbody.innerHTML = '';
            
            logs.forEach(log => {
                const level = (log.log_level || 'info').toLowerCase();
                const row = document.createElement('tr');
                if (level === 'warning') row.className = 'level-warning';
                if (level === 'error') row.className = 'level-error';

                row.innerHTML = `
                    <td class="text-muted small">${log.created_at}</td>
                    <td><span class="badge badge-node btn-xs">${log.sys_id}</span></td>
                    <td class="text-uppercase small fw-bold text-secondary">${log.log_type}</td>
                    <td><span class="small fw-bold">${level.toUpperCase()}</span></td>
                    <td class="text-break">${escapeHtml(log.log_msg)}</td>
                    <td class="font-monospace small">${log.log_code || 0}</td>
                `;
                tbody.appendChild(row);
            });
            document.getElementById('log-count').innerText = `${logs.length} messages`;
        } catch (e) {
            console.error("Fetch Logs Error:", e);
        }
    }

    function escapeHtml(str) {
        if (!str) return "";
        return str.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
    }

    function refreshAll() {
        fetchStatus();
        fetchLogs();
    }

    // 初期起動
    window.onload = () => {
        refreshAll();
        setInterval(refreshAll, CONFIG.REFRESH_INTERVAL);
    };
</script>

</body>
</html>