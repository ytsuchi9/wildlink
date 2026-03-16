<?php
// api_logs.php (リファクタリング版)
require_once 'wildlink_core.php';
header('Content-Type: application/json');

try {
    // system_logsテーブルのカラム名に合わせてSQLを修正
    $stmt = $pdo->query("SELECT created_at, sys_id, log_type, log_level, log_msg 
                         FROM system_logs 
                         ORDER BY created_at DESC LIMIT 50");
    
    echo json_encode($stmt->fetchAll());
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => $e->getMessage()]);
}