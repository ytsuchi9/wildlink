<?php
// /var/www/html/web/get_command_status.php
require_once 'wildlink_core.php';
header('Content-Type: application/json');

/**
 * WildLink 2026 Command Tracker
 * 役割: send_cmd.php で発行したコマンドの進捗を追跡する
 */

$id = isset($_GET['id']) ? (int)$_GET['id'] : 0;

if ($id <= 0) {
    echo json_encode(["error" => "Invalid Command ID"]);
    exit;
}

// 必要な情報を取得
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
    $data = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($data) {
        // --- 💡 2026 状態判定補正ロジック ---
        // 1. まだ完了時刻(completed_at)が入っていないなら、問答無用で 'pending'。
        // 2. ステータスがNULL、または空文字の場合も 'pending' として扱う。
        if (empty($data['completed_at']) || empty($data['val_status']) || $data['val_status'] === 'NULL') {
            $data['val_status'] = 'pending';
        }

        // 実行結果詳細のデコード
        if (!empty($data['val_res_payload'])) {
            $data['detail'] = json_decode($data['val_res_payload'], true);
        } else {
            $data['detail'] = null;
        }

        $data['log_code'] = (int)$data['log_code'];
        echo json_encode($data);
    } else {
        http_response_code(404);
        echo json_encode([
            "val_status" => "not_found", 
            "error" => "Command ID: $id not found"
        ]);
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        "val_status" => "error", 
        "error" => $e->getMessage()
    ]);
}