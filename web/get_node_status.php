<?php
header('Content-Type: application/json');

// シンボリックリンクを考慮した絶対パス解決
// /opt/wildlink/web/get_node_status.php の1つ上がプロジェクトルート
$env_path = '/opt/wildlink/.env'; 

if (file_exists($env_path)) {
    $lines = file($env_path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        if (strpos(trim($line), '#') === 0) continue;
        $parts = explode('=', $line, 2);
        if (count($parts) === 2) {
            $key = trim($parts[0]);
            $val = trim($parts[1], " \t\n\r\0\x0B\"'");
            $_ENV[$key] = $val;
            putenv("$key=$val");
        }
    }
}

require_once('db_config.php'); // db_config.php内では $_ENV を参照

$node_id = $_GET['node_id'] ?? 'node_001';

try {
    // 変数名チェック: $pdo ではなく $mysqli が存在するか確認
    if (!isset($mysqli)) {
        throw new Exception("Database connection (\$mysqli) not found.");
    }

    // --- 1. バイタル取得 (system_logs) ---
    $sql_v = "SELECT sys_cpu_t, net_rssi FROM system_logs WHERE sys_id = ? ORDER BY id DESC LIMIT 1";
    $stmt_v = $mysqli->prepare($sql_v);
    $stmt_v->bind_param("s", $node_id);
    $stmt_v->execute();
    $vitals_row = $stmt_v->get_result()->fetch_assoc();
    // データがない場合は '--' を入れた連想配列を代入して、JS側のエラーを防ぐ
    $vitals = $vitals_row ?: [
        'sys_cpu_t' => '--',
        'net_rssi' => '--'
    ];

    // --- 2. ユニット状態の結合取得 (node_configs + node_status_current) ---
    $sql_s = "
        SELECT c.vst_type, IFNULL(s.val_status, 'idle') as val_status 
        FROM node_configs c
        LEFT JOIN node_status_current s ON c.sys_id = s.sys_id AND c.vst_type = s.vst_type
        WHERE c.sys_id = ?
    ";
    $stmt_s = $mysqli->prepare($sql_s);
    $stmt_s->bind_param("s", $node_id);
    $stmt_s->execute();
    $res_s = $stmt_s->get_result();
    
    $unit_statuses = [];
    while ($row = $res_s->fetch_assoc()) {
        $unit_statuses[$row['vst_type']] = $row['val_status'];
    }

    // --- 3. 最新環境データ (node_data) ---
    $sql_d = "SELECT raw_data FROM node_data WHERE sys_id = ? ORDER BY id DESC LIMIT 1";
    $stmt_d = $mysqli->prepare($sql_d);
    $stmt_d->bind_param("s", $node_id);
    $stmt_d->execute();
    $env_row = $stmt_d->get_result()->fetch_assoc();
    $env_data = json_decode($env_row['raw_data'] ?? '{}', true);

    // 全て成功したら JSON を返す
    echo json_encode([
        'status' => 'success',
        'vitals' => $vitals,
        'unit_statuses' => $unit_statuses,
        'env_data' => $env_data,
        'server_time' => date('H:i:s')
    ]);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['status' => 'error', 'msg' => $e->getMessage()]);
}