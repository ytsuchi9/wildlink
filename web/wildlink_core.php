<?php
// WES 2026 Core Module
class WildLinkCore {
    protected $pdo;

    public function __construct() {
        $host = 'localhost';
        $db   = 'wildlink_db'; // 実際のDB名に合わせてください
        $user = 'ytsuchi';     // User Summaryに基づき設定
        $pass = 'your_password'; 
        $charset = 'utf8mb4';

        $dsn = "mysql:host=$host;dbname=$db;charset=$charset";
        $options = [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES   => false,
        ];

        try {
            $this->pdo = new PDO($dsn, $user, $pass, $options);
        } catch (\PDOException $e) {
            header('Content-Type: application/json', true, 500);
            echo json_encode(['error' => 'DB Connection Failed']);
            exit;
        }
    }

    // 共通のレスポンスヘッダー
    public function sendJson($data) {
        header('Content-Type: application/json');
        echo json_encode($data);
    }
}