<?php
// /var/www/html/db_config.php

$db_host = "localhost";
$db_user = "watcher_user";
$db_pass = "your_password"; // 昨日設定したパスワード
$db_name = "field_watcher";

$mysqli = new mysqli($db_host, $db_user, $db_pass, $db_name);

if ($mysqli->connect_error) {
    die("Connection failed: " . $mysqli->connect_error);
}

// 文字コードをUTF-8に設定
$mysqli->set_charset("utf8mb4");
?>