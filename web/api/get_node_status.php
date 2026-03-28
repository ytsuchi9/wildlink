<?php
/**
 * WildLink 2026 Node Status Aggregator
 * 役割: 全ノードの基本情報、バイタル(sys_cpu_t/net_rssi)、およびデバイス状態(vst_states)を統合して返す
 * 参照DB: nodes (基本), system_logs (バイタル), node_status_current (デバイス状態)
 */

ob_start();
ini_set('display_errors', 0);
error_reporting(E_ALL);

require_once dirname(__DIR__) . '/wildlink_core.php';

header('Content-Type: application/json; charset=utf-8');

try {
    global $pdo;
    if (!$pdo) throw new Exception("DB Connection Failed");

    // 1. ノード一覧と、最新の 'report' ログ（バイタル入り）を取得
    // ※ nodes テーブルに sys_id, sys_status, val_log_level 等がある前提
    $sql = "SELECT 
                n.sys_id, 
                n.sys_status, 
                n.val_log_level,
                l.sys_cpu_t,
                l.net_rssi,
                l.created_at as last_seen
            FROM nodes n
            LEFT JOIN system_logs l ON l.id = (
                SELECT id FROM system_logs 
                WHERE sys_id = n.sys_id AND log_type = 'report'
                ORDER BY id DESC LIMIT 1
            )
            ORDER BY n.sys_id ASC";

    $stmt = $pdo->query($sql);
    $nodes = $stmt->fetchAll(PDO::FETCH_ASSOC);

    foreach ($nodes as &$node) {
        // 2. node_status_current から、そのノードに属する全デバイスの状態を取得
        $sql_vst = "SELECT vst_role_name, val_status 
                    FROM node_status_current 
                    WHERE sys_id = ?";
        $stmt_vst = $pdo->prepare($sql_vst);
        $stmt_vst->execute([$node['sys_id']]);
        $node['vst_states'] = $stmt_vst->fetchAll(PDO::FETCH_ASSOC);

        // 3. sys_monitor.php の表示用キー名へのマッピング
        // DB上の sys_cpu_t を JSが期待する sys_cpu_temp に入れる
        $node['sys_cpu_temp'] = $node['sys_cpu_t'];
        
        // 4. 生存判定 (5分 = 300秒 以内に report ログがあればオンライン)
        $is_online = false;
        if ($node['last_seen']) {
            $last_ts = strtotime($node['last_seen']);
            if ((time() - $last_ts) < 300) {
                // status が active かつ、タイムスタンプが新しい場合のみ真
                if ($node['sys_status'] === 'active') {
                    $is_online = true;
                }
            }
        }
        $node['is_online'] = $is_online;

        // 5. 更新日時の整形（フロント表示用）
        $node['updated_at'] = $node['last_seen'] ?: 'Never';
    }

    ob_clean();
    echo json_encode(["nodes" => $nodes], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);

} catch (Exception $e) {
    if (ob_get_length()) ob_clean();
    http_response_code(500);
    echo json_encode([
        "status" => "error", 
        "message" => "Fleet Status Error: " . $e->getMessage()
    ], JSON_UNESCAPED_UNICODE);
}
ob_end_flush();