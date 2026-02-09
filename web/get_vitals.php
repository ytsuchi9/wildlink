<?php
// /var/www/html/get_vitals.php
ini_set('display_errors', 1);
error_reporting(E_ALL);
require_once 'db_config.php';

// JSONとして返すことを宣言
header('Content-Type: application/json');

$cam_id = $_GET['cam_id'] ?? '';
if (!$cam_id) { 
    echo json_encode(["error" => "no id provided"]); 
    exit; 
}

try {
    // 1. node_status テーブルから最新のステータスを取得
    $stmt = $mysqli->prepare("SELECT * FROM node_status WHERE node_id = ?");
    $stmt->bind_param("s", $cam_id);
    $stmt->execute();
    $status_data = $stmt->get_result()->fetch_assoc();
    $stmt->close();

    if (!$status_data) {
        echo json_encode(["error" => "node not found"]);
        exit;
    }

    // 2. command_logs テーブルから最新のログを20件取得
    // スクロールを堪能するために多めに取得します
    $stmt_log = $mysqli->prepare("SELECT command, status, message, created_at FROM command_logs WHERE node_id = ? ORDER BY created_at DESC LIMIT 20");
    $stmt_log->bind_param("s", $cam_id);
    $stmt_log->execute();
    $log_res = $stmt_log->get_result();

    $logs = [];
    while($l = $log_res->fetch_assoc()){
        $time_str = date('H:i:s', strtotime($l['created_at']));
        // message があればそれを表示、なければ status を表示
        $detail = !empty($l['message']) ? $l['message'] : $l['status'];
        $logs[] = "[$time_str] " . $l['command'] . " (" . $detail . ")";
    }
    $stmt_log->close();

    // 3. 全データをまとめてJSONで返却
    echo json_encode([
        "temp"         => $status_data['cpu_temp'] ?? '--',
        "motion_state" => (isset($status_data['motion_enabled']) && $status_data['motion_enabled'] == 1 ? 'ACTIVE' : 'inactive'),
        "is_online"    => (int)($status_data['is_online'] ?? 0),
        "updated_at"   => isset($status_data['last_seen']) ? date('H:i:s', strtotime($status_data['last_seen'])) : '--',
        "logs"         => $logs
    ]);

} catch (Exception $e) {
    echo json_encode(["error" => $e->getMessage()]);
}

$mysqli->close();