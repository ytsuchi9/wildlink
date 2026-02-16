<?php
// get_node_config.php
require_once 'db_config.php'; // ここで $mysqli を取得
header('Content-Type: application/json');

$node_id = $_GET['node_id'] ?? 'node_001';

// node_configs テーブルから取得（命名規則に基づき val_params 等を使用）
$sql = "SELECT vst_type, val_params FROM node_configs WHERE sys_id = ?";
$stmt = $mysqli->prepare($sql);
$stmt->bind_param("s", $node_id);
$stmt->execute();
$result = $stmt->get_result();

$configs = [];
while ($row = $result->fetch_assoc()) {
    // val_params はJSON文字列として保存されている前提でパース
    $row['val_params'] = json_decode($row['val_params'], true);
    $configs[] = $row;
}

echo json_encode($configs);
$mysqli->close();