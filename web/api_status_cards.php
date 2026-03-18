<?php
// /var/www/html/web/api_status_cards.php
require_once 'wildlink_core.php';
header('Content-Type: application/json');

/**
 * WildLink 2026 Fleet Status API
 * 役割: 全ノードの最新状態とバイタルを一覧で取得する
 */

try {
    // 1. 最新のシステムログのみを抽出する一時テーブル的な結合
    // system_logs の log_type='report' を優先的に取得
    $sql = "SELECT 
                n.sys_id, 
                n.sys_status, 
                n.val_log_level,
                n.net_ip,
                l.ext_info,
                l.created_at as last_seen
            FROM nodes n
            LEFT JOIN system_logs l ON l.id = (
                SELECT id FROM system_logs 
                WHERE sys_id = n.sys_id AND log_type = 'report'
                ORDER BY id DESC LIMIT 1
            )
            ORDER BY n.sys_id ASC";

    $stmt = $pdo->query($sql);
    $nodes = $stmt->fetchAll();

    foreach ($nodes as &$node) {
        // 2. ext_info (JSON) のデコードとマージ
        $cpu_t = '--';
        $rssi  = '--';
        
        if (!empty($node['ext_info'])) {
            $ext = json_decode($node['ext_info'], true);
            if (is_array($ext)) {
                $cpu_t = $ext['cpu_t'] ?? ($ext['sys_cpu_t'] ?? '--');
                $rssi  = $ext['rssi']  ?? ($ext['net_rssi']  ?? '--');
            }
        }
        
        // レスポンスをフラットにする
        $node['sys_cpu_t'] = $cpu_t;
        $node['net_rssi']  = $rssi;
        
        // 3. 生存判定 (5分以上通信がなければ警告)
        $is_stale = true;
        if ($node['last_seen']) {
            $last_ts = strtotime($node['last_seen']);
            if ((time() - $last_ts) < 300) { // 300秒(5分)以内
                $is_stale = false;
            }
        }
        $node['is_online'] = ($node['sys_status'] === 'active' && !$is_stale);
        
        // 不要なカラムは削除して軽量化
        unset($node['ext_info']);
    }

    echo json_encode($nodes);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["error" => "Fleet Status Error: " . $e->getMessage()]);
}