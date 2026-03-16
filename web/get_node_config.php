<?php
// get_node_config.php
require_once 'wildlink_core.php';
header('Content-Type: application/json');

$sys_id = $_GET['sys_id'] ?? 'node_001';

try {
    // 以前のコードで使われていた正しいテーブル名: node_configs, device_catalog
    $sql = "SELECT 
                nc.vst_type, 
                nc.vst_role_name, 
                nc.vst_description, 
                nc.val_unit_map, 
                nc.hw_driver, 
                nc.hw_bus_addr, 
                dc.vst_class, 
                dc.ui_component_type, 
                nc.val_params, 
                nc.val_enabled 
            FROM node_configs nc
            JOIN device_catalog dc ON nc.vst_type = dc.vst_type
            WHERE nc.sys_id = ?";

    $stmt = $pdo->prepare($sql);
    $stmt->execute([$sys_id]);
    $configs = $stmt->fetchAll();

    foreach ($configs as &$row) {
        // 文字列のまま入っているJSONを配列にデコード
        $row['val_params'] = json_decode($row['val_params'] ?? '{}', true);
        $row['val_unit_map'] = json_decode($row['val_unit_map'] ?? 'null', true);
        $row['val_enabled'] = (int)($row['val_enabled'] ?? 0);
    }

    echo json_encode($configs);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => $e->getMessage()]);
}