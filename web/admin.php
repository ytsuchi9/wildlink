<?php
// /var/www/html/admin.php
ini_set('display_errors', 1);
error_reporting(E_ALL);
require_once 'db_config.php';

// データベースからノード取得
$result = $mysqli->query("SELECT * FROM node_status ORDER BY node_id");
$nodes = [];
while($r = $result->fetch_assoc()) {
    $nodes[] = $r;
}
?>
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pi-Eye Central Monitor v5.2</title>
    <style>
        body { background: #121212; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; margin: 0; padding-bottom: 50px; }
        h1 { background: #2c3e50; color: white; padding: 20px; margin: 0; font-size: 1.5em; border-bottom: 4px solid #27ae60; }
        .container { display: flex; flex-wrap: wrap; gap: 20px; padding: 20px; }
        .card { background: #1e1e1e; padding: 20px; border-radius: 12px; width: 380px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); border-top: 6px solid #444; }
        .card.online { border-top-color: #27ae60; } 
        .card.offline { border-top-color: #c0392b; opacity: 0.8; }
        .status-badge { font-size: 0.6em; padding: 4px 10px; border-radius: 20px; }
        .online .status-badge { background: #27ae60; color: white; }
        .offline .status-badge { background: #c0392b; color: white; }
        .vital-info { background: #2a2a2a; padding: 12px; border-radius: 6px; margin: 10px 0; font-family: monospace; color: #00ff00; font-size: 0.9em; border-left: 3px solid #444; }
        .controls { display: flex; gap: 10px; margin-bottom: 10px; }
        button { cursor: pointer; border: none; border-radius: 4px; font-weight: bold; padding: 10px; }
        .btn-start { background: #27ae60; color: white; flex: 1; }
        .btn-stop { background: #c0392b; color: white; flex: 1; }
        .btn-link { background: #34495e; color: white; width: 100%; margin-bottom: 15px; }
        .config-mini { background: #252525; padding: 12px; border-radius: 6px; margin-bottom: 15px; border: 1px solid #333; }
        select { background: #333; color: #fff; border: 1px solid #555; font-size: 0.85em; padding: 4px; border-radius: 3px; flex: 1; }
        .btn-apply { background: #636e72; color: white; padding: 5px 10px; font-size: 0.8em; }
        .log-box { background: #000; color: #0f0; height: 200px; overflow-y: auto; padding: 10px; border-radius: 4px; font-size: 0.82em; }
        .log-entry { margin-bottom: 4px; border-bottom: 1px dashed #222; }
    </style>

    <script>
        /**
         * 💡 重要: スクリプトを head 内に配置し、
         * "Not Defined" エラーを防ぐために関数を先に定義します。
         */
        function sendCmd(camId, command, payload = '') {
            console.log(`Sending: ${command} to ${camId}, Data: ${payload}`);
            const fd = new FormData();
            fd.append('cam_id', camId);
            fd.append('command', command);
            fd.append('payload', payload); // PHP側の期待するキー名
            
            fetch('send_cmd.php', { method: 'POST', body: fd })
                .then(r => r.text())
                .then(t => console.log(`Result: ${t}`))
                .catch(e => console.error("Send Error:", e));
        }

        function applySettings(camId) {
            const proto = document.getElementById(`proto-${camId}`).value;
            const camType = document.getElementById(`cam-${camId}`).value;
            const configData = JSON.stringify({ protocol: proto, camera: camType });
            
            if(confirm(`${camId} の設定を更新しますか？\n[${proto} / ${camType}]`)) {
                sendCmd(camId, 'update_config', configData);
            }
        }

        function refreshNode(camId) {
            fetch(`get_vitals.php?cam_id=${camId}`)
                .then(r => r.json())
                .then(data => {
                    if(!data) return;
                    document.getElementById(`card-${camId}`).className = data.is_online ? 'card online' : 'card offline';
                    document.getElementById(`badge-${camId}`).innerText = data.is_online ? 'ONLINE' : 'OFFLINE';
                    document.getElementById(`vital-${camId}`).innerHTML = `Temp: ${data.temp}°C | PIR: ${data.motion_state}<br>🕒 ${data.updated_at}`;

                    const logBox = document.getElementById(`log-${camId}`);
                    // 💡 data.logs が null や undefined の場合でもエラーにならないようにガード
                    if (data.logs && Array.isArray(data.logs)) {
                        const logHtml = data.logs.slice().reverse().map(log => {
                            let color = "#0f0"; let icon = "📝";
                            if (log.includes("Command") || log.includes("update")) { color = "#3498db"; icon = "📤"; }
                            else if (log.includes("DETECTED")) { color = "#f1c40f"; icon = "🏃"; }
                            else if (log.includes("🚨") || log.includes("Error")) { color = "#ff4757"; icon = "🚨"; }
                            else if (log.includes("✅") || log.includes("Fixed")) { color = "#2ed573"; icon = "✅"; }
                            else if (log.includes("Starting")) { color = "#55efc4"; icon = "⚡"; }
                            return `<div class="log-entry" style="color: ${color}">${icon} ${log}</div>`;
                        }).join('');
                        logBox.innerHTML = logHtml;
                    }
                }).catch(e => console.error("Fetch Vital Error:", e));
        }
    </script>
</head>
<body>

<h1>🛡️ Pi-Eye Central Monitor v5.2</h1>

<div class="container">
    <?php foreach($nodes as $node): $cam_id = $node['node_id']; ?>
    <div class="card" id="card-<?php echo $cam_id; ?>">
        <h2>
            📷 <?php echo strtoupper($cam_id); ?>
            <span class="status-badge" id="badge-<?php echo $cam_id; ?>">Wait...</span>
        </h2>
        
        <div class="vital-info" id="vital-<?php echo $cam_id; ?>">Loading Vitals...</div>

        <div class="controls">
            <button class="btn-start" onclick="sendCmd('<?php echo $cam_id; ?>', 'start_motion')">▶ 監視開始</button>
            <button class="btn-stop" onclick="sendCmd('<?php echo $cam_id; ?>', 'stop_motion')">⏹ 監視停止</button>
        </div>

        <button class="btn-link" onclick="window.open('index.php?cam=<?php echo $cam_id; ?>')">📂 録画フォルダ</button>

        <div class="config-mini">
            <div class="config-row" style="display:flex; gap:5px;">
                <select id="proto-<?php echo $cam_id; ?>">
                    <option value="tcp">TCP</option>
                    <option value="udp">UDP</option>
                </select>
                <select id="cam-<?php echo $cam_id; ?>">
                    <option value="csi">CSI Cam</option>
                    <option value="usb">USB Cam</option>
                </select>
                <button class="btn-apply" onclick="applySettings('<?php echo $cam_id; ?>')">適用</button>
            </div>
        </div>

        <div class="log-box" id="log-<?php echo $cam_id; ?>">Waiting for logs...</div>
    </div>
    <script>
        // 各カードごとに初期化とタイマーを開始
        refreshNode('<?php echo $cam_id; ?>');
        setInterval(() => refreshNode('<?php echo $cam_id; ?>'), 3000);
    </script>
    <?php endforeach; ?>
</div>

</body>
</html>