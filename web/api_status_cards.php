<?php
// api_status_cards.php (リファクタリング版)
require_once 'wildlink_core.php';
header('Content-Type: application/json');

try {
    // nodesテーブルの sys_status を正しく参照
    $sql = "SELECT n.sys_id, n.sys_status, n.val_log_level,
                   l.sys_cpu_t, l.net_rssi, l.created_at as last_seen
            FROM nodes n
            LEFT JOIN (
                SELECT sys_id, sys_cpu_t, net_rssi, created_at
                FROM system_logs
                WHERE id IN (SELECT MAX(id) FROM system_logs GROUP BY sys_id)
            ) l ON n.sys_id = l.sys_id";

    $stmt = $pdo->query($sql);
    echo json_encode($stmt->fetchAll());
} catch (Exception $e) {
    echo json_encode(["error" => $e->getMessage()]);
}