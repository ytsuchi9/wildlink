<?php
// /var/www/html/get_command_status.php
require_once 'db_config.php';
header('Content-Type: application/json');

$id = $_GET['id'] ?? 0;

$sql = "SELECT val_status, log_code, sent_at, acked_at, completed_at FROM node_commands WHERE id = ?";

try {
    $stmt = $mysqli->prepare($sql);
    $stmt->bind_param("i", $id);
    $stmt->execute();
    $result = $stmt->get_result();
    $data = $result->fetch_assoc();

    if ($data) {
        echo json_encode($data);
    } else {
        echo json_encode(["error" => "Command not found"]);
    }
} catch (Exception $e) {
    echo json_encode(["error" => $e->getMessage()]);
}
$mysqli->close();