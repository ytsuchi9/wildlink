<?php
header('Content-Type: application/json; charset=UTF-8');

// 1. 設定ファイルの読み込み
$config_file = 'master_config.json';
if (!file_exists($config_file)) {
    echo json_encode(["status" => "error", "message" => "設定ファイルが見つかりません"]);
    exit;
}

$config = json_decode(file_get_contents($config_file), true);
$broker_ip = $config['broker_ip'];

// 2. リクエスト解析
$cam_id = $_POST['cam_id'] ?? '';

// 3. バリデーション
if (!isset($config['cameras'][$cam_id])) {
    echo json_encode(["status" => "error", "message" => "無効なカメラID: $cam_id"]);
    exit;
}

$cam_name = $config['cameras'][$cam_id]['name'];

// 4. MQTTコマンド送信 (mosquitto_pub)
$topic = "cmnd/{$cam_id}/camera";
$message = "ON";
$command = "mosquitto_pub -h " . escapeshellarg($broker_ip) . " -t " . escapeshellarg($topic) . " -m " . escapeshellarg($message) . " 2>&1";

$output = shell_exec($command);

// 5. レスポンス
if (is_null($output) || $output === "") {
    echo json_encode([
        "status" => "success",
        "message" => "[$cam_name] へ起動指示を送信しました",
        "debug" => "Topic: $topic"
    ], JSON_UNESCAPED_UNICODE);
} else {
    echo json_encode([
        "status" => "error", 
        "message" => "MQTT送信失敗",
        "dev_detail" => $output
    ], JSON_UNESCAPED_UNICODE);
}