<?php
// get_command_status.php
require_once 'wildlink_core.php'; // mysqli + db_config ではなくこちらを使用
header('Content-Type: application/json');

$id = $_GET['id'] ?? 0;

// 2026年仕様：node_commandsテーブルを参照
$sql = "SELECT val_status, log_code, created_at, completed_at FROM node_commands WHERE id = ?";

try {
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$id]);
    $data = $stmt->fetch();

    if ($data) {
        // JS側が val_status を見て判定するので、そのまま返す
        echo json_encode($data);
    } else {
        http_response_code(404);
        echo json_encode(["error" => "Command not found"]);
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => $e->getMessage()]);
}
// PDOはスクリプト終了時に自動切断されるため $mysqli->close() は不要