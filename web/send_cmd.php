<?php
// send_cmd.php
ini_set('display_errors', 1);
error_reporting(E_ALL);
require_once 'db_config.php';

$cam_id  = $_POST['cam_id']  ?? '';
$command = $_POST['command'] ?? '';
$payload = $_POST['payload'] ?? '';

if (!$cam_id || !$command) {
    echo "Error: Missing parameters";
    exit;
}

// 1. MQTT送信先トピックの修正 (規約: wildlink/{node_id}/cmd)
$topic = "wildlink/" . $cam_id . "/cmd";

// 2. メッセージ内容の修正 (main_manager.py が判定している文字列へ)
if ($command === 'start_motion' || $command === 'start') {
    $mqtt_msg = "cam_start";
} elseif ($command === 'stop_motion' || $command === 'stop') {
    $mqtt_msg = "cam_stop";
} else {
    // その他の汎用コマンド
    $mqtt_msg = $command; 
}

// --- 1. MQTT送信 (ここはOK) ---
$topic = "wildlink/" . $cam_id . "/cmd";
$mqtt_msg = ($command === 'start_motion' || $command === 'start') ? "cam_start" : "cam_stop";
exec("mosquitto_pub -t " . escapeshellarg($topic) . " -m " . escapeshellarg($mqtt_msg));

// --- 2. DB記録 (ここを修正) ---
// カラムを sys_id, act_type, status の3つに絞った場合
$sql = "INSERT INTO command_logs (sys_id, act_type, status) VALUES (?, ?, 'sent')";
$stmt = $mysqli->prepare($sql);

if ($stmt) {
    // 引数は2つ: 1つ目の?に $cam_id, 2つ目の?に $mqtt_msg
    // 'ss' は String, String の意味です
    $stmt->bind_param("ss", $cam_id, $mqtt_msg);
    
    if ($stmt->execute()) {
        echo "Success: Published '$mqtt_msg' to $topic";
    } else {
        echo "Execute Error: " . $stmt->error;
    }
    $stmt->close();
} else {
    echo "SQL Prepare Error: " . $mysqli->error;
}

$mysqli->close();