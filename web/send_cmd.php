<?php
// send_cmd.php
require_once 'db_config.php';
header('Content-Type: application/json');

$sys_id = $_POST['node_id'] ?? 'node_001';
$cmd    = $_POST['cmd']     ?? ''; 
$params = $_POST['val']     ?? ''; 

// カラム名は cmd_type であることを確認済み
$sql = "INSERT INTO node_commands (sys_id, cmd_type, cmd_json, val_status) VALUES (?, ?, ?, 'pending')";
$stmt = $mysqli->prepare($sql);
$stmt->bind_param("sss", $sys_id, $cmd, $params);

if ($stmt->execute()) {
    echo json_encode(["val_status" => "success", "log_msg" => "Command accepted"]);
} else {
    echo json_encode(["val_status" => "error", "log_msg" => $mysqli->error]);
}

$mysqli->close();