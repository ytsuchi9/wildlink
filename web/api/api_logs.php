<?php
/**
 * WildLink 2026 System Log API
 * 役割: システムログ・イベントログをフィルタリングして取得する
 * 配置: /var/www/html/web/api/api_logs.php (または api_logs.php)
 */

require_once '../wildlink_core.php';

// CORSやキャッシュ無効化の設定（デバッグ・リアルタイム性重視）
header('Content-Type: application/json');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');

// パラメータ取得
$sys_id    = $_GET['sys_id']    ?? null;
$log_type  = $_GET['log_type']  ?? null; // 'event' か 'system' か
$log_level = $_GET['log_level'] ?? null;
$limit     = isset($_GET['limit']) ? (int)$_GET['limit'] : 50;

try {
    $where_clauses = [];
    $params = [];

    // 1. 動的なクエリ組み立て
    if ($sys_id && $sys_id !== 'all') {
        $where_clauses[] = "sys_id = ?";
        $params[] = $sys_id;
    }
    
    if ($log_type) {
        $where_clauses[] = "log_type = ?";
        $params[] = $log_type;
    }

    if ($log_level) {
        // 大文字小文字を問わず比較
        $where_clauses[] = "UPPER(log_level) = UPPER(?)";
        $params[] = $log_level;
    }

    // カラム名は DB設計(log_level, log_msg, log_code)に準拠
    $sql = "SELECT created_at, sys_id, log_type, log_level, log_code, log_msg, log_ext 
            FROM system_logs";

    if (!empty($where_clauses)) {
        $sql .= " WHERE " . implode(" AND ", $where_clauses);
    }

    // 最新のものを上に（降順）、同秒の場合はID等で安定させる
    $sql .= " ORDER BY created_at DESC, id DESC LIMIT " . $limit;

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $logs = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // 2. データの整形
    foreach ($logs as &$log) {
        $log['log_code'] = (int)($log['log_code'] ?? 0);
        
        // log_ext に JSON が入っている場合は、デコードして配列として返すとJS側で扱いやすい
        if (!empty($log['log_ext'])) {
            $decoded = json_decode($log['log_ext'], true);
            if (json_last_error() === JSON_ERROR_NONE) {
                $log['log_ext'] = $decoded;
            }
        }
    }

    echo json_encode($logs, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        "error" => "Log Fetch Error",
        "message" => $e->getMessage()
    ]);
}