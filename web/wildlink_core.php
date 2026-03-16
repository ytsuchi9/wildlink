<?php
// /var/www/html/wildlink_core.php

/**
 * WildLink 2026 Core Engine
 * 役割: 環境変数読み込み、DB接続の集約、共通ユーティリティ
 */

class WildLink {
    private static $env = null;
    public static $pdo = null;
    public static $mysqli = null;

    // 1. 環境設定の読み込み
    public static function init() {
        if (self::$env !== null) return;

        $env_path = '/opt/wildlink/.env';
        if (!file_exists($env_path)) $env_path = '/home/ytsuchi/wildlink/.env';

        if (file_exists($env_path)) {
            foreach (file($env_path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
                $line = trim($line);
                if (strpos($line, '#') === 0 || $line === '') continue;
                $parts = explode('=', $line, 2);
                if (count($parts) === 2) {
                    $val = explode('#', $parts[1], 2)[0]; // コメント除去
                    self::$env[trim($parts[0])] = trim($val, " \t\n\r\0\x0B\"'");
                }
            }
        }
        self::connectDB();
    }

    // 2. DB接続 (PDO & MySQLi 両対応)
    private static function connectDB() {
        $host = self::$env['DB_HOST_LOCAL'] ?? (self::$env['DB_HOST'] ?? '127.0.0.1');
        $db   = self::$env['DB_NAME'] ?? 'wildlink_db';
        $user = self::$env['DB_USER'] ?? 'ytsuchi';
        $pass = self::$env['DB_PASS'] ?? '';

        try {
            // 新世代用 PDO
            self::$pdo = new PDO("mysql:host=$host;dbname=$db;charset=utf8mb4", $user, $pass, [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC
            ]);
            // 既存コード用 MySQLi
            self::$mysqli = new mysqli($host, $user, $pass, $db);
            self::$mysqli->set_charset("utf8mb4");
        } catch (Exception $e) {
            header('Content-Type: application/json');
            die(json_encode(["error" => "Critical: DB Connection Failed"]));
        }
    }

    // 3. ヘルパー：最新バイタル取得
    public static function getLatestVital($sys_id) {
        $stmt = self::$pdo->prepare("SELECT * FROM system_logs WHERE sys_id = ? ORDER BY id DESC LIMIT 1");
        $stmt->execute([$sys_id]);
        return $stmt->fetch();
    }
}

// 自動初期化
WildLink::init();
// 短縮変数（既存コード書き換え用）
$pdo = WildLink::$pdo;
$mysqli = WildLink::$mysqli;