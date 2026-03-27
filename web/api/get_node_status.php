<?php
// /var/www/html/web/api/get_node_status.php
require_once '../wildlink_core.php';
header('Content-Type: application/json');

$sys_id = $_GET['sys_id'] ?? null; 

if (!$sys_id) {
    echo json_encode(["error" => "No sys_id provided"]);
    exit;
}

try {
    // 1. nodesテーブルから基本情報を取得
    $stmt = $pdo->prepare("SELECT sys_id, sys_status, val_log_level, net_ip FROM nodes WHERE sys_id = ?");
    $stmt->execute([$sys_id]);
    $node = $stmt->fetch();

    if (!$node) {
        echo json_encode(["error" => "Node [{$sys_id}] not found"]);
        exit;
    }

    // 2. 2026年仕様：役割(Role)ごとの最新状態を取得
    // node_configsをベースに、現在のステータスをJOINする
    $sqlStatus = "
        SELECT 
            c.vst_role_name, 
            c.vst_type, 
            COALESCE(s.val_status, 'offline') as val_status,
            s.updated_at
        FROM node_configs c
        LEFT JOIN node_status_current s 
            ON c.sys_id = s.sys_id AND c.vst_role_name = s.vst_role_name
        WHERE c.sys_id = ? AND c.is_active = 1
    ";
    $stmtStatus = $pdo->prepare($sqlStatus);
    $stmtStatus->execute([$sys_id]);
    $roles = $stmtStatus->fetchAll();

    // 3. 最新バイタルを取得 (wildlink_coreの拡張版を使用)
    $vital = WildLink::getLatestVital($sys_id);

    // 4. レスポンスの構築
    $response = [
        "sys_id"     => $node['sys_id'],
        "sys_status" => $node['sys_status'],
        "net_ip"     => $node['net_ip'],
        "roles"      => $roles, // 役割ごとの配列
        "vitals"     => [
            "sys_cpu_t" => $vital['cpu_t'] ?? '--', // ext_infoから自動マージされた値
            "net_rssi"  => $vital['rssi'] ?? '--',
            "board_t"   => $vital['board_t'] ?? '--',
            "last_seen" => $vital['created_at'] ?? '--'
        ],
        "server_time" => date('H:i:s')
    ];

    echo json_encode($response);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => $e->getMessage()]);
}