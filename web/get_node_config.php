<?php
require_once 'db_config.php';
header('Content-Type: application/json');

$node_id = $_GET['node_id'] ?? 'node_001';

// 新設したカラム (vst_role_name, vst_description, val_unit_map, hw_driver, hw_bus_addr) を追加
$sql = "SELECT nc.vst_type, nc.vst_role_name, nc.vst_description, nc.val_unit_map, 
               nc.hw_driver, nc.hw_bus_addr, dc.vst_class, dc.ui_component_type, 
               nc.val_params, nc.val_enabled 
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
        // JSON形式で追加した unit_map もデコードしておく
        $row['val_unit_map'] = json_decode($row['val_unit_map'] ?? 'null', true);
        $row['val_enabled'] = (int)$row['val_enabled'];
        $configs[] = $row;
    }
    echo json_encode($configs);
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => $e->getMessage()]);
}
$mysqli->close();