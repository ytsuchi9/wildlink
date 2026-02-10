<?php
// db_config.php

// .envファイルを読み込む
$env = parse_ini_file(__DIR__ . '/.env');

if (!$env) {
    die("Error: .env file not found.");
}

$db_host = $env['DB_HOST'];
$db_name = $env['DB_NAME'];
$db_user = $env['DB_USER'];
$db_pass = $env['DB_PASS'];

$mysqli = new mysqli($db_host, $db_user, $db_pass, $db_name);

if ($mysqli->connect_error) {
    // セキュリティのため、エラー詳細にパスワードを含めないよう注意
    die("Database Connection failed.");
}

$mysqli->set_charset("utf8mb4");