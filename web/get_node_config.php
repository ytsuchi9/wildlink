<?php
// /var/www/html/web/get_node_config.php
require_once 'wildlink_core.php';
header('Content-Type: application/json');

/**
 * WildLink 2026 Role-Based Config Fetcher
 * 役割: 指定されたsys_idに紐づく全てのデバイス設定と現在のステータスを結合して取得する
 */

$sys_id = $_GET['sys_id'] ?? 'node_001';

try {
    // 2026年仕様：Property層(val_enabled)とStatus情報を明示的に取得
    $sql = "SELECT 
                nc.vst_type, 
                nc.vst_role_name, 
                nc.val_enabled,      -- 追記：動作フラグ
                nc.vst_description, 
                nc.val_unit_map, 
                nc.hw_driver, 
                nc.hw_bus_addr, 
                dc.vst_class, 
                dc.vst_module,
                dc.ui_component_type, 
                nc.val_params, 
                nc.is_active,        -- Meta層：レコード有効性
                IFNULL(ns.val_status, 'idle') as val_status, 
                ns.updated_at as last_update
            FROM node_configs nc
            LEFT JOIN device_catalog dc ON nc.vst_type = dc.vst_type
            LEFT JOIN node_status_current ns ON nc.sys_id = ns.sys_id AND nc.vst_role_name = ns.vst_role_name
            WHERE nc.sys_id = ? 
              AND nc.is_active = 1 -- 追記：最新レコードのみに絞り込み
            ORDER BY nc.vst_role_name ASC";

    $stmt = $pdo->prepare($sql);
    $stmt->execute([$sys_id]);
    $configs = $stmt->fetchAll();

    foreach ($configs as &$row) {
        // JSON文字列を配列にデコード
        $row['val_params']   = json_decode($row['val_params'] ?? '{}', true);
        $row['val_unit_map'] = json_decode($row['val_unit_map'] ?? 'null', true);
        
        // 数値型へのキャスト
        $row['val_enabled']  = (int)($row['val_enabled'] ?? 1);
        $row['is_active']    = (int)($row['is_active'] ?? 0);

        // カタログ未登録時のフォールバック
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