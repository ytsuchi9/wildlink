<?php
// get_node_status.php
require_once 'db_config.php';
header('Content-Type: application/json');

$node_id = $_GET['node_id'] ?? 'node_001';

// 最新の1件を取得 (raw_data を含む全カラム)
$sql = "SELECT * FROM node_status WHERE sys_id = ? ORDER BY id DESC LIMIT 1";
$stmt = $mysqli->prepare($sql);
$stmt->bind_param("s", $node_id);
$stmt->execute();
$result = $stmt->get_result();

if ($row = $result->fetch_assoc()) {
    echo json_encode($row);
} else {
    echo json_encode(["val_status" => "offline"]);
}

$mysqli->close();