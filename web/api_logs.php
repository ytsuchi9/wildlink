<?php
// api_logs.php
header('Content-Type: application/json');

// 1. .env の場所
$env_path = '/opt/wildlink/.env'; 
if (!file_exists($env_path)) {
    $env_path = '/home/ytsuchi/wildlink/.env';
}

// 2. .env をパース（行末コメント対応版）
$env = [];
if (file_exists($env_path)) {
    $lines = file($env_path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        $line = trim($line);
        if (strpos($line, '#') === 0 || $line === '') continue;

        // まず = で分割
        $parts = explode('=', $line, 2);
        if (count($parts) === 2) {
            $key = trim($parts[0]);
            $val = trim($parts[1]);

            // 💡 値の途中にある '#' 以降（コメント）を削除
            // ただし、クォーテーションで囲まれている場合は考慮が必要ですが、
            // 今回はシンプルに '#' で分割して先頭を取ります
            if (strpos($val, '#') !== false) {
                $val = explode('#', $val, 2)[0];
            }

            // 最後に空白やクォーテーションを綺麗にする
            $env[$key] = trim($val, " \t\n\r\0\x0B\"'");
        }
    }
} else {
    die(json_encode(["error" => ".env file not found"]));
}

// 3. 接続情報のセットアップ
// ここで取り出した $db_host が "127.0.0.1" だけになるはずです
$db_host = $env['DB_HOST_LOCAL'] ?? ($env['DB_HOST'] ?? '127.0.0.1');
$db_user = $env['DB_USER'] ?? 'ytsuchi';
$db_pass = $env['DB_PASS'] ?? '';
$db_name = $env['DB_NAME'] ?? 'wildlink_db';

try {
    $pdo = new PDO(
        "mysql:host=$db_host;dbname=$db_name;charset=utf8mb4",
        $db_user,
        $db_pass,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
    );

    $stmt = $pdo->query("SELECT created_at, sys_id, log_type, log_level, log_msg 
                         FROM system_logs 
                         ORDER BY created_at DESC LIMIT 50");
    $logs = $stmt->fetchAll(PDO::FETCH_ASSOC);

    echo json_encode($logs);

} catch (PDOException $e) {
    http_response_code(500);
    // 💡 エラー詳細を出して、ホスト名が変になっていないか再確認できるようにします
    echo json_encode([
        "error" => "DB Connection failed",
        "detail" => $e->getMessage(),
        "debug_host" => $db_host // 念のためここに出力
    ]);
}