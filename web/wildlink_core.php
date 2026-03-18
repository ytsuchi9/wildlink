<?php
// /var/www/html/wildlink_core.php

/**
 * WildLink 2026 Core Engine
 * 役割: 環境変数読み込み、DB接続の集約、共通ユーティリティ
 * 2026 Update: Role-aware data fetching & Unified Logging
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

    // 2. DB接続
    private static function connectDB() {
        $host = self::$env['DB_HOST_LOCAL'] ?? (self::$env['DB_HOST'] ?? '127.0.0.1');
        $db   = self::$env['DB_NAME'] ?? 'wildlink_db';
        $user = self::$env['DB_USER'] ?? 'ytsuchi';
        $pass = self::$env['DB_PASS'] ?? '';

        try {
            self::$pdo = new PDO("mysql:host=$host;dbname=$db;charset=utf8mb4", $user, $pass, [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC
            ]);
            self::$mysqli = new mysqli($host, $user, $pass, $db);
            self::$mysqli->set_charset("utf8mb4");
        } catch (Exception $e) {
            header('Content-Type: application/json');
            die(json_encode(["error" => "Critical: DB Connection Failed"]));
        }
    }

    /**
     * ヘルパー：ノードの最新システムログ（Vital）取得
     * ※CPU温度やRSSIなど、システム全般の状態
     */
    public static function getLatestVital($sys_id) {
        $stmt = self::$pdo->prepare("
            SELECT * FROM system_logs 
            WHERE sys_id = ? AND log_type = 'report'
            ORDER BY created_at DESC LIMIT 1
        ");
        $stmt->execute([$sys_id]);
        $res = $stmt->fetch();
        
        // ext_info (JSON) がある場合はデコードしてマージ
        if ($res && !empty($res['ext_info'])) {
            $ext = json_decode($res['ext_info'], true);
            if (is_array($ext)) $res = array_merge($res, $ext);
        }
        return $res;
    }

    /**
     * ヘルパー：特定の役割（Role）の最新データを取得
     * 例：BME280センサーの最新の温度・湿度など
     */
    public static function getLatestRoleData($sys_id, $role_name = 'node_system') {
        $stmt = self::$pdo->prepare("
            SELECT * FROM node_data 
            WHERE sys_id = ? AND vst_role_name = ? 
            ORDER BY created_at DESC LIMIT 1
        ");
        $stmt->execute([$sys_id, $role_name]);
        $res = $stmt->fetch();

        if ($res && !empty($res['raw_data'])) {
            $raw = json_decode($res['raw_data'], true);
            if (is_array($raw)) $res['val_data'] = $raw;
        }
        return $res;
    }

    /**
     * ヘルパー：ノードに紐づくアクティブなVST（役割）一覧を取得
     */
    public static function getNodeActiveRoles($sys_id) {
        $stmt = self::$pdo->prepare("
            SELECT vst_role_name, vst_type, val_status 
            FROM node_configs 
            WHERE sys_id = ? AND is_active = 1
        ");
        $stmt->execute([$sys_id]);
        return $stmt->fetchAll();
    }
}

// 自動初期化
WildLink::init();
$pdo = WildLink::$pdo;
$mysqli = WildLink::$mysqli;