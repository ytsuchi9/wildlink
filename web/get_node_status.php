<?php
// get_node_status.php
require_once 'wildlink_core.php';
header('Content-Type: application/json');

// 修正：$_GET['id'] ではなく $_GET['sys_id'] を見る
$sys_id = $_GET['sys_id'] ?? 'node_001'; 

try {
    // 2. nodesテーブルから基本情報を取得
    $stmt = $pdo->prepare("SELECT sys_id, sys_status, val_log_level, net_ip FROM nodes WHERE sys_id = ?");
    $stmt->execute([$sys_id]);
    $node = $stmt->fetch();

    if (!$node) {
        echo json_encode(["error" => "Node [{$sys_id}] not found"]);
        exit;
    }

    // 3. ユニットごとの動作状態を取得
    $stmtStatus = $pdo->prepare("SELECT vst_type, val_status FROM node_status_current WHERE sys_id = ?");
    $stmtStatus->execute([$sys_id]);
    $unitStatuses = $stmtStatus->fetchAll(PDO::FETCH_KEY_PAIR);

    // 4. 最新バイタルを取得
    $vital = WildLink::getLatestVital($sys_id);

    // 5. レスポンスの構築
    $response = [
        "sys_id"        => $node['sys_id'],
        "sys_status"    => $node['sys_status'],
        "unit_statuses" => $unitStatuses, 
        "vitals"        => [
            "sys_cpu_t"   => $vital['sys_cpu_t'] ?? '--',
            "net_rssi"    => $vital['net_rssi'] ?? '--',
            "sys_up"      => $vital['sys_up'] ?? '--',
            "last_seen"   => $vital['created_at'] ?? '--'
        ],
        "server_time"   => date('H:i:s')
    ];

    echo json_encode($response);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => $e->getMessage()]);
}