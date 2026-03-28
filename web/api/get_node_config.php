<?php
/**
 * WildLink 2026 Role-Based Config Fetcher (Safe Edition)
 * 役割: 指定されたsys_idに紐づく全てのデバイス設定と現在のステータスを結合して取得する
 */

// 1. 出力ガード: 予期せぬエラー文字列がJSONに混入するのを防ぐ
ob_start();

// デバッグ設定（開発中は 1, 本番は 0）
ini_set('display_errors', 0);
error_reporting(E_ALL);

require_once dirname(__DIR__) . '/wildlink_core.php';

// ヘッダー設定
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');

$sys_id = $_GET['sys_id'] ?? 'node_001';

try {
    // wildlink_core.php 内で初期化された $pdo を使用
    global $pdo;

    if (!isset($pdo) || $pdo === null) {
        throw new Exception("Database connection (\$pdo) is not initialized.");
    }

    // 2026年仕様：Property層(val_enabled)とStatus情報を結合取得
    $sql = "SELECT 
                nc.vst_type, 
                nc.vst_role_name, 
                nc.val_enabled,
                nc.vst_description, 
                nc.val_unit_map, 
                nc.hw_driver, 
                nc.hw_bus_addr, 
                dc.vst_class, 
                dc.vst_module,
                dc.ui_component_type, 
                nc.val_params, 
                nc.is_active,
                IFNULL(ns.val_status, 'idle') as val_status, 
                ns.updated_at as last_update
            FROM node_configs nc
            LEFT JOIN device_catalog dc ON nc.vst_type = dc.vst_type
            LEFT JOIN node_status_current ns ON nc.sys_id = ns.sys_id AND nc.vst_role_name = ns.vst_role_name
            WHERE nc.sys_id = ? 
              AND nc.is_active = 1 
            ORDER BY nc.vst_role_name ASC";

    $stmt = $pdo->prepare($sql);
    $stmt->execute([$sys_id]);
    $configs = $stmt->fetchAll(PDO::FETCH_ASSOC);

    foreach ($configs as &$row) {
        // JSON文字列を配列に安全にデコード
        $row['val_params']   = json_decode($row['val_params'] ?? '{}', true) ?: (object)[];
        $row['val_unit_map'] = json_decode($row['val_unit_map'] ?? 'null', true);
        
        // 型の適正化
        $row['val_enabled']  = (int)($row['val_enabled'] ?? 1);
        $row['is_active']    = (int)($row['is_active'] ?? 0);

        // カタログ未登録時（sys_logger等）のフォールバック強化
        if (empty($row['vst_class'])) {
            $row['vst_class'] = 'System';
            $row['ui_component_type'] = 'monitor';
        }
        
        // vst_module が NULL の場合のデフォルト値設定
        if (empty($row['vst_module'])) {
            $row['vst_module'] = 'generic_module';
        }
    }

    // 2. 正常終了: バッファをクリアして純粋なJSONのみを出力
    ob_clean();
    echo json_encode($configs, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);

} catch (Exception $e) {
    // 3. エラー発生時
    if (ob_get_length()) ob_clean();
    
    http_response_code(500);
    echo json_encode([
        "status" => "error",
        "message" => "Config Fetch Error: " . $e->getMessage()
    ], JSON_UNESCAPED_UNICODE);
}

// バッファを閉じる
ob_end_flush();