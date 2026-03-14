<?php
// api_status_cards.php
header('Content-Type: application/json');

$env_path = '/opt/wildlink/.env'; 
if (!file_exists($env_path)) $env_path = '/home/ytsuchi/wildlink/.env';

$env = [];
if (file_exists($env_path)) {
    foreach (file($env_path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $line = trim($line);
        if (strpos($line, '#') === 0 || $line === '') continue;
        $parts = explode('=', $line, 2);
        if (count($parts) === 2) {
            $val = explode('#', trim($parts[1]), 2)[0];
            $env[trim($parts[0])] = trim($val, " \t\n\r\0\x0B\"'");
        }
    }
}

$db_host = $env['DB_HOST_LOCAL'] ?? ($env['DB_HOST'] ?? '127.0.0.1');

try {
    $pdo = new PDO("mysql:host=$db_host;dbname={$env['DB_NAME']};charset=utf8mb4", $env['DB_USER'], $env['DB_PASS']);
    
    // 💡 カラム名エラーを避けるため、確実に存在する sys_id を主軸にする
    // 生存判定(status)は、過去5分以内にログがあるかで動的に判定する
    $sql = "SELECT 
                n.sys_id, 
                'unknown' as val_log_level, -- 後で取得できれば上書き
                l.sys_cpu_t as cpu_t,
                l.net_rssi as rssi,
                l.created_at as last_seen,
                CASE 
                    WHEN l.created_at >= NOW() - INTERVAL 5 MINUTE THEN 'online'
                    ELSE 'offline'
                END as val_status
            FROM nodes n
            LEFT JOIN (
                SELECT sys_id, sys_cpu_t, net_rssi, created_at
                FROM system_logs
                WHERE id IN (SELECT MAX(id) FROM system_logs GROUP BY sys_id)
            ) l ON n.sys_id = l.sys_id";
            
    $stmt = $pdo->query($sql);
    $res = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    echo json_encode($res ?: []);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(["error" => $e->getMessage(), "sql" => $sql]);
}