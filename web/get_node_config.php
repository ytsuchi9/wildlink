<?php
require_once 'db_config.php';
header('Content-Type: application/json');

$node_id = $_GET['node_id'] ?? 'node_001';

// dc.ui_component_type を追加して JOIN
$sql = "SELECT nc.vst_type, dc.vst_class, dc.ui_component_type, nc.val_params, nc.val_enabled 
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
        // 文字列のまま ui_component_type を追加
        $configs[] = $row;
    }
    echo json_encode($configs);
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => $e->getMessage()]);
}
$mysqli->close();