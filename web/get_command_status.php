<?php
// /var/www/html/web/get_command_status.php
require_once 'wildlink_core.php';
header('Content-Type: application/json');

/**
 * WildLink 2026 Command Tracker
 * 役割: send_cmd.php で発行したコマンドの進捗（pending -> sent -> success/error）を追跡する
 */

$id = isset($_GET['id']) ? (int)$_GET['id'] : 0;

if ($id <= 0) {
    echo json_encode(["error" => "Invalid Command ID"]);
    exit;
}

// 2026年仕様：詳細な実行結果（val_res_payload）も取得対象に含める
$sql = "SELECT 
            val_status, 
            log_code, 
            val_res_payload, 
            created_at, 
            completed_at 
        FROM node_commands 
        WHERE id = ?";

try {
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$id]);
    $data = $stmt->fetch();

    if ($data) {
        // JSONデータがあればデコードしてレスポンスに含める
        if (!empty($data['val_res_payload'])) {
            $data['detail'] = json_decode($data['val_res_payload'], true);
        } else {
            $data['detail'] = null;
        }

        // log_code は数値として返す
        $data['log_code'] = (int)$data['log_code'];

        echo json_encode($data);
    } else {
        http_response_code(404);
        echo json_encode(["status" => "not_found", "error" => "Command ID: $id not found"]);
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["status" => "error", "error" => $e->getMessage()]);
}