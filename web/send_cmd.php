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

// 1. MQTT送信 (WildLink仕様のトピックとJSON構造へ)
$topic = "wildlink/" . $cam_id . "/control";

// camviewer.html から 'start_motion' が送られてきたら 'start' に変換
if ($command === 'start_motion') {
    $mqtt_data = ["act_stream" => "start"];
} elseif ($command === 'stop_motion') {
    $mqtt_data = ["act_stream" => "stop"];
} else {
    $mqtt_data = ["command" => $command, "payload" => $payload];
}

$mqtt_msg = json_encode($mqtt_data);
$cmd_exec = "mosquitto_pub -t " . escapeshellarg($topic) . " -m " . escapeshellarg($mqtt_msg);
exec($cmd_exec);

// 2. DB記録（ここでエラーが起きていないかチェック）
$sql = "INSERT INTO command_logs (node_id, command, status, message) VALUES (?, ?, 'sent', ?)";
$stmt = $mysqli->prepare($sql);
if (!$stmt) {
    echo "SQL Prepare Error: " . $mysqli->error;
    exit;
}

$log_msg = $payload ?: "Command Issued";
$stmt->bind_param("sss", $cam_id, $command, $log_msg);

if ($stmt->execute()) {
    echo "Success: Logged $command for $cam_id";
} else {
    echo "Execute Error: " . $stmt->error;
}

$stmt->close();
$mysqli->close();