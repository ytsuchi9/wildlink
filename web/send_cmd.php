<?php
// /var/www/html/send_cmd.php
require_once 'db_config.php';

header('Content-Type: application/json');

// JS側から送られてくる値を取得
$node_id  = $_POST['node_id'] ?? 'node_001';
$cmd_type = $_POST['cmd_type'] ?? 'vst_control'; // 何の操作か
$cmd_json = $_POST['cmd_json'] ?? '{}';         // 変更パッチ内容

// 1. DB (node_commands) に「予約」としてインサート
// val_status はデフォルトの 'pending' で入ります
$sql = "INSERT INTO node_commands (sys_id, cmd_type, cmd_json, created_at) VALUES (?, ?, ?, NOW(3))";

try {
    $stmt = $mysqli->prepare($sql);
    $stmt->bind_param("sss", $node_id, $cmd_type, $cmd_json);
    
    if ($stmt->execute()) {
        // インサートされたIDを取得してJSに返す
        $new_id = $mysqli->insert_id;
        echo json_encode([
            "status" => "ok",
            "command_id" => $new_id
        ]);
    } else {
        throw new Exception($stmt->error);
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["status" => "error", "message" => $e->getMessage()]);
}

$mysqli->close();