<?php
// /var/www/html/get_node_status.php
require_once 'db_config.php';
header('Content-Type: application/json');

$node_id = $_GET['node_id'] ?? 'node_001';

// created_at を log_at として取得
$sql = "SELECT sys_id, raw_data, created_at as log_at 
        FROM node_data 
        WHERE sys_id = ? 
        ORDER BY created_at DESC LIMIT 1";

try {
    $stmt = $mysqli->prepare($sql);
    $stmt->bind_param("s", $node_id);
    $stmt->execute();
    $result = $stmt->get_result();
    $data = $result->fetch_assoc();

    if ($data) {
        // raw_data(JSON)をパースして sys_status を取り出し、CamViewer用の階層にセット
        $raw_obj = json_decode($data['raw_data'], true);
        $data['sys_status'] = $raw_obj['sys_status'] ?? 'unknown';
        
        echo json_encode($data);
    } else {
        echo json_encode([
            "sys_id" => $node_id,
            "sys_status" => "offline",
            "raw_data" => "{}",
            "log_at" => null
        ]);
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => $e->getMessage()]);
}

$mysqli->close();