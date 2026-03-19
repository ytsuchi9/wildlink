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

// 2026年仕様：詳細な実行結果（val_res_payload）も含めて取得
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
        // completed_at が NULL の間は、DB上の val_status が何であれ 
        // フロントエンドには 'pending' として返し、JSの判定待ちを継続させる。
        if (empty($data['completed_at'])) {
            $data['val_status'] = 'pending';
        }

        // JSONデータ（実行結果の詳細）があればデコード
        if (!empty($data['val_res_payload'])) {
            $data['detail'] = json_decode($data['val_res_payload'], true);
        } else {
            $data['detail'] = null;
        }

        // 数値型を保証
        $data['log_code'] = (int)$data['log_code'];

        echo json_encode($data);
    } else {
        // ID自体が見つからない場合
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