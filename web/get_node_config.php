<?php
require_once 'db_config.php';
header('Content-Type: application/json');

$node_id = $_GET['node_id'] ?? 'node_001';

// log_at は不要なので削除し、正しい JOIN を行います
$sql = "SELECT nc.vst_type, dc.vst_class, nc.val_params, nc.val_enabled 
        FROM node_configs nc
        JOIN device_catalog dc ON nc.vst_type = dc.vst_type
        WHERE nc.sys_id = ?";

try {
    $stmt = $mysqli->prepare($sql);
    $stmt->bind_param("s", $node_id);
    $stmt->execute();
    $result = $stmt->get_result();
    $configs = [];
    while ($row = $result->fetch_assoc()) {
        $row['val_params'] = json_decode($row['val_params'], true);
        $row['val_enabled'] = (int)$row['val_enabled'];
        $configs[] = $row;
    }
    echo json_encode($configs);
} catch (Exception $e) {
    echo json_encode(["error" => $e->getMessage()]);
}
$mysqli->close();