<?php
// /var/www/html/web/get_node_config.php
require_once 'wildlink_core.php';
header('Content-Type: application/json');

$sys_id = $_GET['sys_id'] ?? 'node_001';

try {
    // 2026年仕様：設定(nc)に最新ステータス(ns)を結合して取得
    $sql = "SELECT 
                nc.vst_type, 
                nc.vst_role_name, 
                nc.vst_description, 
                nc.val_unit_map, 
                nc.hw_driver, 
                nc.hw_bus_addr, 
                dc.vst_class, 
                dc.vst_module,
                dc.ui_component_type, 
                nc.val_params, 
                nc.is_active,
                IFNULL(ns.val_status, 'idle') as val_status, -- ステータスを追加（デフォルトidle）
                ns.updated_at as last_update
            FROM node_configs nc
            LEFT JOIN device_catalog dc ON nc.vst_type = dc.vst_type
            LEFT JOIN node_status_current ns ON nc.sys_id = ns.sys_id AND nc.vst_role_name = ns.vst_role_name
            WHERE nc.sys_id = ?
            ORDER BY nc.vst_role_name ASC";

    $stmt = $pdo->prepare($sql);
    $stmt->execute([$sys_id]);
    $configs = $stmt->fetchAll();

    foreach ($configs as &$row) {
        $row['val_params']   = json_decode($row['val_params'] ?? '{}', true);
        $row['val_unit_map'] = json_decode($row['val_unit_map'] ?? 'null', true);
        $row['is_active']    = (int)($row['is_active'] ?? 0);

        if (!$row['vst_class']) {
            $row['vst_class'] = 'Unknown';
            $row['ui_component_type'] = 'default';
        }
    }

    echo json_encode($configs);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => "Config Fetch Error: " . $e->getMessage()]);
}