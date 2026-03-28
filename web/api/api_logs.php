<?php
/**
 * WildLink 2026 System Log API
 */

ob_start();

ini_set('display_errors', 0); 
error_reporting(E_ALL);

// コアモジュールの読み込み
require_once dirname(__DIR__) . '/wildlink_core.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');

// パラメータ取得
$sys_id    = $_GET['sys_id']    ?? null;
$log_type  = $_GET['log_type']  ?? null;
$log_level = $_GET['log_level'] ?? null;
$limit     = isset($_GET['limit']) ? (int)$_GET['limit'] : 50;

try {
    // wildlink_core.php の末尾で定義された $pdo を使用
    global $pdo;

    if (!$pdo) {
        throw new Exception("Database instance not found.");
    }

    $where_clauses = [];
    $params = [];

    if ($sys_id && $sys_id !== 'all') {
        $where_clauses[] = "sys_id = ?";
        $params[] = $sys_id;
    }
    
    if ($log_type) {
        $where_clauses[] = "log_type = ?";
        $params[] = $log_type;
    }

    if ($log_level) {
        $where_clauses[] = "UPPER(log_level) = UPPER(?)";
        $params[] = $log_level;
    }

    $sql = "SELECT created_at, sys_id, log_type, log_level, log_code, log_msg, log_ext FROM system_logs";
    if (!empty($where_clauses)) {
        $sql .= " WHERE " . implode(" AND ", $where_clauses);
    }
    $sql .= " ORDER BY created_at DESC, id DESC LIMIT " . (int)$limit;

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $logs = $stmt->fetchAll(PDO::FETCH_ASSOC);

    foreach ($logs as &$log) {
        $log['log_code'] = (int)($log['log_code'] ?? 0);
        $ext_data = $log['log_ext'] ?? '';
        if (is_string($ext_data) && !empty($ext_data)) {
            $decoded = json_decode($ext_data, true);
            $log['log_ext'] = (json_last_error() === JSON_ERROR_NONE) ? $decoded : $ext_data;
        } else {
            $log['log_ext'] = null;
        }
    }

    ob_clean();
    echo json_encode($logs, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);

} catch (Exception $e) {
    if (ob_get_length()) ob_clean();
    http_response_code(500);
    echo json_encode([
        "status" => "error",
        "message" => $e->getMessage()
    ], JSON_UNESCAPED_UNICODE);
}

ob_end_flush();