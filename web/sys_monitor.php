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
        
        /* ステータスカードのスタイル */
        .card-node { border: none; border-radius: 12px; transition: transform 0.2s; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        .card-node:hover { transform: translateY(-3px); }
        .status-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .online { background-color: #28a745; box-shadow: 0 0 8px #28a745; }
        .offline { background-color: #dc3545; }
        .vital-label { font-size: 0.75rem; color: #6c757d; text-transform: uppercase; }
        .vital-value { font-family: 'Share Tech Mono', monospace; font-size: 1.1rem; }

        /* ログテーブルのスタイル */
        .card-log { border: none; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden; }
        .log-table-container { max-height: 65vh; overflow-y: auto; background: white; }
        .log-table { font-size: 0.88rem; margin-bottom: 0; }
        .log-table thead { position: sticky; top: 0; background: #f8f9fa; z-index: 10; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
        
        /* ログレベル毎の色分け */
        .level-info { color: #0d6efd; }
        .level-warning { color: #856404; background-color: #fff3cd !important; font-weight: bold; }
        .level-error { color: #721c24; background-color: #f8d7da !important; font-weight: bold; }
        .badge-node { background-color: #495057; color: white; font-family: monospace; padding: 0.4em 0.6em; }
        
        .update-flash { animation: flash-bg 1s ease-out; }
        @keyframes flash-bg { from { background-color: #e8f0fe; } to { background-color: transparent; } }
    </style>
</head>
<body>

<header class="monitor-header">
    <div class="container-fluid px-4">
        <div class="d-flex justify-content-between align-items-center">
            <h2 class="brand-title mb-0">🌿 WILDLINK 2026 <span class="fs-5 text-muted ms-2">SYSTEM MONITOR</span></h2>
            <div class="text-end">
                <div id="last-update" class="text-muted small">Last Update: --:--:--</div>
                <div class="mt-1">
                    <button onclick="refreshAll()" class="btn btn-sm btn-dark">Manual Refresh</button>
                </div>
            </div>
        </div>
    </div>
</header>

<div class="container-fluid px-4">
    <div id="node-cards" class="row mb-4">
        <div class="col-12 text-center text-muted">Loading node status...</div>
    </div>

    <div class="card card-log">
        <div class="card-header bg-white py-3 d-flex justify-content-between align-items-center">
            <h5 class="mb-0 fw-bold">Live System Logs</h5>
            <span class="badge bg-primary rounded-pill" id="log-count">0 messages</span>
        </div>
        <div class="log-table-container">
            <table class="table table-hover log-table">
                <thead>
                    <tr>
                        <th style="width: 180px;">Timestamp</th>
                        <th style="width: 120px;">Node ID</th>
                        <th style="width: 140px;">Type</th>
                        <th style="width: 100px;">Level</th>
                        <th>Message</th>
                    </tr>
                </thead>
                <tbody id="log-body">
                    </tbody>
            </table>
        </div>
    </div>
</div>

<script>
    // --- 1. ログデータの取得と反映 ---
    async function fetchLogs() {
        try {
            const response = await fetch('api_logs.php');
            if (!response.ok) throw new Error('Network response was not ok');
            const logs = await response.json();
            
            const tableBody = document.getElementById('log-body');
            const logCountBadge = document.getElementById('log-count');
            
            tableBody.innerHTML = '';
            logs.forEach(log => {
                const row = document.createElement('tr');
                const level = log.log_level.toLowerCase();
                const levelClass = `level-${level}`;
                
                row.className = level === 'info' ? '' : levelClass;
                row.innerHTML = `
                    <td class="text-muted small">${log.created_at}</td>
                    <td><span class="badge badge-node">${log.sys_id}</span></td>
                    <td class="text-uppercase small fw-bold text-secondary">${log.log_type || 'system'}</td>
                    <td><span class="fw-bold">${log.log_level.toUpperCase()}</span></td>
                    <td>${escapeHtml(log.log_msg)}</td>
                `;
                tableBody.appendChild(row);
            });
            logCountBadge.innerText = `${logs.length} messages`;
        } catch (error) {
            console.error('Log Fetch Error:', error);
        }
    }

    // --- 2. ステータスカードの取得と反映 ---
    async function fetchStatusCards() {
        try {
            const response = await fetch('api_status_cards.php');
            const nodes = await response.json();
            const container = document.getElementById('node-cards');
            
            container.innerHTML = '';
            nodes.forEach(node => {
                const isOnline = node.val_status === 'online';
                const statusClass = isOnline ? 'online' : 'offline';
                
                const cardHtml = `
                    <div class="col-md-3 col-sm-6 mb-3">
                        <div class="card card-node p-3 h-100">
                            <div class="d-flex justify-content-between align-items-start mb-3">
                                <div>
                                    <div class="vital-label">Node ID</div>
                                    <div class="fw-bold fs-5">${node.sys_id}</div>
                                </div>
                                <span class="badge bg-light text-dark border">${node.val_log_level}</span>
                            </div>
                            <div class="mb-3">
                                <span class="status-dot ${statusClass}"></span>
                                <span class="fw-bold text-uppercase">${node.val_status}</span>
                            </div>
                            <div class="row g-0 border-top pt-2">
                                <div class="col-6 border-end text-center">
                                    <div class="vital-label">CPU Temp</div>
                                    <div class="vital-value">${node.cpu_t ? parseFloat(node.cpu_t).toFixed(1) + '°C' : '--'}</div>
                                </div>
                                <div class="col-6 text-center">
                                    <div class="vital-label">RSSI</div>
                                    <div class="vital-value">${node.rssi || '--'}<small class="fs-6 ps-1">dBm</small></div>
                                </div>
                            </div>
                            <div class="mt-2 text-center">
                                <small class="text-muted" style="font-size: 0.7rem;">Seen: ${node.last_seen || 'Never'}</small>
                            </div>
                        </div>
                    </div>
                `;
                container.innerHTML += cardHtml;
            });
        } catch (error) {
            console.error('Status Card Error:', error);
        }
    }

    // --- 共通ツール ---
    function escapeHtml(str) {
        if (!str) return "";
        return str.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
    }

    function refreshAll() {
        fetchLogs();
        fetchStatusCards();
        document.getElementById('last-update').innerText = `Last Update: ${new Date().toLocaleTimeString()}`;
    }

    // --- 初期化とループ実行 ---
    window.onload = () => {
        refreshAll();
        // 5秒ごとに自動更新
        setInterval(refreshAll, 5000);
    };
</script>

</body>
</html>