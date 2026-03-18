<?php
// /var/www/html/web/api_logs.php
require_once 'wildlink_core.php';
header('Content-Type: application/json');

/**
 * WildLink 2026 System Log API
 * 役割: 過去のシステムログをフィルタリング・取得する
 */

$sys_id    = $_GET['sys_id']    ?? null;
$log_level = $_GET['log_level'] ?? null;
$limit     = isset($_GET['limit']) ? (int)$_GET['limit'] : 50;

try {
    $where_clauses = [];
    $params = [];

    // 1. 動的なクエリ組み立て
    if ($sys_id) {
        $where_clauses[] = "sys_id = ?";
        $params[] = $sys_id;
    }
    if ($log_level) {
        $where_clauses[] = "log_level = ?";
        $params[] = $log_level;
    }

    $sql = "SELECT created_at, sys_id, log_type, log_level, log_code, log_msg 
            FROM system_logs";

    if (!empty($where_clauses)) {
        $sql .= " WHERE " . implode(" AND ", $where_clauses);
    }

    $sql .= " ORDER BY created_at DESC LIMIT " . $limit;

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $logs = $stmt->fetchAll();

    // 2. 数値型を確実に数値として返す
    foreach ($logs as &$log) {
        $log['log_code'] = (int)($log['log_code'] ?? 0);
    }

    echo json_encode($logs);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => "Log Fetch Error: " . $e->getMessage()]);
}