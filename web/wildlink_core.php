<?php
/**
 * WildLink 2026 Core Module
 * 役割: 環境変数の読み込みとデータベース接続の管理
 * 履歴: .envのDB_HOST_LOCAL/REMOTE設計に対応
 */

class WildLinkCore {
    private $pdo;
    private $env = [];

    public function __construct() {
        // 1. .env ファイルの読み込み
        $this->loadEnv(dirname(__DIR__) . '/.env');

        // 2. 接続先の決定ロジック
        // Web API（Hub自身）で動作する場合は LOCAL を優先
        $host = $this->getEnv('DB_HOST_LOCAL');
        if (!$host) {
            $host = $this->getEnv('DB_HOST', '127.0.0.1');
        }

        $db_name = $this->getEnv('DB_NAME', 'wildlink_db');
        $user    = $this->getEnv('DB_USER', 'ytsuchi');
        $pass    = $this->getEnv('DB_PASS', '');
        $charset = $this->getEnv('DB_CHARSET', 'utf8mb4');

        // charsetのサニタイズ（不可視文字除去）
        $charset = preg_replace('/[^a-zA-Z0-9]/', '', $charset);

        $dsn = "mysql:host=$host;dbname=$db_name;charset=$charset";
        $options = [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES   => false,
        ];

        try {
            $this->pdo = new PDO($dsn, $user, $pass, $options);
        } catch (\PDOException $e) {
            $this->handleError("Database connection failed: " . $e->getMessage() . " (Host: $host)");
        }
    }

    /**
     * .envファイルをパースして内部変数に保持する
     */
    private function loadEnv($path) {
        if (!file_exists($path)) return;
        
        $lines = file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
        foreach ($lines as $line) {
            $line = trim($line);
            if ($line === '' || strpos($line, '#') === 0) continue;

            if (strpos($line, '=') !== false) {
                // コメントが含まれる場合（例: VAR=VAL # comment）に対応
                $parts = explode('#', $line, 2);
                $kv = explode('=', $parts[0], 2);
                
                $name = trim($kv[0]);
                $value = isset($kv[1]) ? trim($kv[1]) : '';

                // 引用符を除去
                $value = trim($value, " \t\n\r\0\x0B\"'");
                
                $this->env[$name] = $value;
            }
        }
    }

    public function getEnv($key, $default = null) {
        return $this->env[$key] ?? getenv($key) ?? $default;
    }

    public function getPdo() {
        return $this->pdo;
    }

    private function handleError($message) {
        if (!headers_sent()) {
            header('Content-Type: application/json; charset=utf-8', true, 500);
        }
        echo json_encode([
            'status' => 'error',
            'message' => $message
        ], JSON_UNESCAPED_UNICODE);
        exit;
    }
}

// グローバルインスタンスの作成
$core = new WildLinkCore();
$pdo = $core->getPdo();