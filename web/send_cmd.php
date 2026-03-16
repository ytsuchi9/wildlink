<?php
// send_cmd.php
require_once 'wildlink_core.php';
header('Content-Type: application/json');

// 1. POSTデータの取得名を sys_id に統一
$sys_id   = $_POST['sys_id'] ?? null; 
$cmd_type = $_POST['cmd_type'] ?? 'vst_control';
$cmd_json = $_POST['cmd_json'] ?? null;

if (!$sys_id || !$cmd_json) {
    echo json_encode(["error" => "Missing required parameters: sys_id or cmd_json"]);
    exit;
}

try {
    // 2. 2026年仕様：node_commandsテーブルへ挿入
    $sql = "INSERT INTO node_commands (sys_id, cmd_type, cmd_json, val_status, created_at) 
            VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP(3))";
    
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$sys_id, $cmd_type, $cmd_json]);

    echo json_encode([
        "success" => true,
        "command_id" => $pdo->lastInsertId(),
        "msg" => "Command queued successfully"
    ]);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => $e->getMessage()]);
}