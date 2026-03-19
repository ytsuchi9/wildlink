<?php
// /var/www/html/web/send_cmd.php
require_once 'wildlink_core.php';
header('Content-Type: application/json');

/**
 * WildLink 2026 Command Dispatcher (Role-Based)
 * 役割: UIからの操作をDBのキュー（node_commands）に高速検索可能な形で登録する
 */

// 1. パラメータの取得
$sys_id   = $_POST['sys_id']   ?? null; 
$cmd_type = $_POST['cmd_type'] ?? 'vst_control';
$cmd_json = $_POST['cmd_json'] ?? null;

// JSONをデコードして、role（役割名）を特定
$payload = json_decode($cmd_json, true);
$role    = $payload['role'] ?? $payload['target'] ?? null;

// バリデーション
if (!$sys_id || !$cmd_json || !$role) {
    http_response_code(400);
    echo json_encode(["error" => "Missing required parameters: sys_id, role, or cmd_json"]);
    exit;
}

try {
    // 2. ペイロードの正規化 (JSON内にも sys_id と role を確実に入れ込む)
    $payload['sys_id'] = $sys_id;
    if (!isset($payload['role'])) {
        $payload['role'] = $role;
    }
    $final_cmd_json = json_encode($payload);

    // 3. 2026年仕様：vst_role_name カラムへの直接書き込み
    // CURRENT_TIMESTAMP(3) でミリ秒まで記録し、実行順序を保証します
    $sql = "INSERT INTO node_commands (
                sys_id, 
                vst_role_name, 
                cmd_type, 
                cmd_json, 
                val_status, 
                log_note, 
                created_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, CURRENT_TIMESTAMP(3))";
    
    $log_msg = "Queued from WebUI: " . ($payload['action'] ?? 'execute');

    $stmt = $pdo->prepare($sql);
    $stmt->execute([
        $sys_id, 
        $role,           // 役割名（高速検索用）
        $cmd_type, 
        $final_cmd_json, // 補完済みフルペイロード
        $log_msg         // 初期ログ
    ]);

    // 4. レスポンス（CameraUnit.js の track() メソッドがこれを受け取る）
    echo json_encode([
        "success" => true,
        "command_id" => $pdo->lastInsertId(),
        "target_role" => $role,
        "status" => "pending",
        "msg" => "Command successfully queued for [$role]"
    ]);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => "Command Dispatch Error: " . $e->getMessage()]);
}