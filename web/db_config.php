<?php
// db_config.php

$realPath = dirname(realpath(__FILE__)); 
$envPath = $realPath . '/../.env';

if (!file_exists($envPath)) {
    header('Content-Type: application/json');
    die(json_encode(["val_status" => "error", "log_msg" => "Env file not found at: " . $envPath]));
}

// parse_ini_file を使わず、1行ずつ読み込む
$env = [];
$lines = file($envPath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
foreach ($lines as $line) {
    if (strpos(trim($line), '#') === 0) continue; // コメント行を無視
    if (strpos($line, '=') !== false) {
        list($name, $value) = explode('=', $line, 2);
        // 前後の空白やクォーテーションを除去
        $env[trim($name)] = trim($value, " \t\n\r\0\x0B\"'");
    }
}

if (empty($env)) {
    header('Content-Type: application/json');
    die(json_encode(["val_status" => "error", "log_msg" => "Error: .env file is empty or invalid."]));
}

$mysqli = new mysqli($env['DB_HOST'], $env['DB_USER'], $env['DB_PASS'], $env['DB_NAME']);

if ($mysqli->connect_error) {
    header('Content-Type: application/json');
    die(json_encode(["val_status" => "error", "log_msg" => "DB Connection failed: " . $mysqli->connect_error]));
}

$mysqli->set_charset("utf8mb4");