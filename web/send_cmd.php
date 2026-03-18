<?php
// /var/www/html/web/send_cmd.php
require_once 'wildlink_core.php';
header('Content-Type: application/json');

/**
 * WildLink 2026 Command Dispatcher
 * 役割: UIからの操作をDBのキュー（node_commands）に登録する
 */

// 1. パラメータの取得
$sys_id   = $_POST['sys_id']   ?? null; 
$cmd_type = $_POST['cmd_type'] ?? 'vst_control';
$cmd_json = $_POST['cmd_json'] ?? null;

// JSONをデコードして、role（役割名）を特定する
$payload = json_decode($cmd_json, true);
$role = $payload['role'] ?? $payload['target'] ?? null;

if (!$sys_id || !$cmd_json || !$role) {
    echo json_encode(["error" => "Missing required parameters: sys_id, role(in json), or cmd_json"]);
    exit;
}

try {
    // 2. ペイロードの正規化 (2026年仕様: sys_id と role を確実に入れ込む)
    $payload['sys_id'] = $sys_id;
    if (!isset($payload['role'])) {
        $payload['role'] = $role;
    }
    $final_cmd_json = json_encode($payload);

    // 3. 2026年仕様：vst_role_name カラムを含めて挿入
    // これにより hub_manager が「どの役割への命令か」を即座に判断できる
    $sql = "INSERT INTO node_commands (sys_id, vst_role_name, cmd_type, cmd_json, val_status, created_at) 
            VALUES (?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP(3))";
    
    $stmt = $pdo->prepare($sql);
    $stmt->execute([
        $sys_id, 
        $role,           // 追加: 役割名
        $cmd_type, 
        $final_cmd_json  // 補完済みのJSON
    ]);

    echo json_encode([
        "success" => true,
        "command_id" => $pdo->lastInsertId(),
        "target_role" => $role,
        "msg" => "Command queued for [$role] on node [$sys_id]"
    ]);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => $e->getMessage()]);
}