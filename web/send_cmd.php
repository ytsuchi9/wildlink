<?php
// /var/www/html/send_cmd.php
require_once 'db_config.php';

// デバッグ用：何が届いたかログに残す
file_put_contents('cmd_debug.log', print_r($_POST, true), FILE_APPEND);

$node_id = $_POST['node_id'] ?? 'node_001';
$cmd = $_POST['cmd'] ?? 'cam';
$val = $_POST['val'] ?? '{}';

$topic = "vst/{$node_id}/cmd/{$cmd}";

// 確実にトピックと中身を指定して実行
$shell_cmd = "mosquitto_pub -h localhost -t '$topic' -m '$val' 2>&1";
$output = shell_exec($shell_cmd);

// 実行結果もログに残す
file_put_contents('cmd_debug.log', "Result: $output\n", FILE_APPEND);

echo json_encode(["status" => "ok", "debug" => $output]);