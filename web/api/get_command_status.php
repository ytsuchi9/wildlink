<?php
// /var/www/html/api/get_command_status.php
require_once dirname(__DIR__) . '/wildlink_core.php';
header('Content-Type: application/json');

/**
 * WildLink 2026 Command Tracker
 * 役割: 発行したコマンドの進捗を追跡する
 */

$id = isset($_GET['id']) ? (int)$_GET['id'] : 0;

if ($id <= 0) {
    echo json_encode(["val_status" => "error", "error" => "Invalid Command ID"]);
    exit;
}

// ログに基づき、現在のテーブル名 'node_commands' を使用します
$tableName = "node_commands"; 

$sql = "SELECT 
            val_status, 
            log_code, 
            val_res_payload, 
            created_at, 
            completed_at 
        FROM $tableName 
        WHERE id = ?";

try {
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$id]);
    $data = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($data) {
        // --- 💡 状態判定ロジックの強化 ---
        
        // 1. completed_at が NULL かつ val_status が 'sent' や 'NULL' の場合はまだ実行中
        if (empty($data['completed_at']) && ($data['val_status'] === 'sent' || empty($data['val_status']) || $data['val_status'] === 'NULL')) {
            $data['val_status'] = 'pending';
        }
        
        // 2. もし val_status が 'streaming' や 'success' になっていれば完了とみなす
        // (ノード側が直接テーブルを書き換えた場合への対応)
        if ($data['val_status'] === 'streaming' || $data['val_status'] === 'active') {
            $data['val_status'] = 'success';
        }

        // 実行結果詳細のデコード
        if (!empty($data['val_res_payload'])) {
            $data['detail'] = json_decode($data['val_res_payload'], true);
        } else {
            $data['detail'] = null;
        }

        $data['log_code'] = (int)($data['log_code'] ?? 0);
        echo json_encode($data);
    } else {
        echo json_encode([
            "val_status" => "not_found", 
            "error" => "Command ID: $id not found in $tableName table"
        ]);
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        "val_status" => "error", 
        "error" => "Database Error: " . $e->getMessage()
    ]);
}