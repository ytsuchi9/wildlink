<?php
/**
 * WildLink 2026 Command Tracker API
 * 役割: 発行したコマンド(node_commands)の進捗状況を追跡する
 */

// 出力バッファリング開始（予期せぬ出力を防ぐ）
ob_start();

ini_set('display_errors', 0);
error_reporting(E_ALL);

require_once dirname(__DIR__) . '/wildlink_core.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');

$id = isset($_GET['id']) ? (int)$_GET['id'] : 0;

if ($id <= 0) {
    ob_clean();
    echo json_encode([
        "val_status" => "error", 
        "log_code" => 400,
        "error" => "Invalid Command ID"
    ]);
    exit;
}

try {
    global $pdo;
    
    // node_commands テーブルから進捗を取得
    $sql = "SELECT 
                val_status, 
                log_code, 
                log_msg,
                val_res_payload, 
                created_at, 
                completed_at 
            FROM node_commands 
            WHERE id = ?";

    $stmt = $pdo->prepare($sql);
    $stmt->execute([$id]);
    $data = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($data) {
        // --- 💡 状態判定ロジックの強化 (WES 2026 準拠) ---
        
        // 1. ノード側がまだ反応していない場合のフォールバック
        // completed_at が空で、ステータスが初期値(sent等)の場合は 'pending' として UI に返す
        if (empty($data['completed_at']) && 
           ($data['val_status'] === 'sent' || empty($data['val_status']) || $data['val_status'] === 'NULL')) {
            $data['val_status'] = 'pending';
        }
        
        // 2. 実行中状態の正規化
        // ストリーミング開始コマンドなどで、ノードが 'active' や 'streaming' を返した場合も、
        // フロントエンドが扱いやすいように 'success' 属性を付与するか、そのまま通す
        if ($data['val_status'] === 'streaming' || $data['val_status'] === 'active') {
            // 必要に応じてここでステータスを丸めることも可能ですが、
            // 2026年仕様では詳細な状態をそのまま返すのが望ましいです。
        }

        // 実行結果詳細（JSON）のデコード
        if (!empty($data['val_res_payload'])) {
            $decoded = json_decode($data['val_res_payload'], true);
            $data['detail'] = (json_last_error() === JSON_ERROR_NONE) ? $decoded : $data['val_res_payload'];
        } else {
            $data['detail'] = null;
        }

        // 数値型のキャスト
        $data['log_code'] = (int)($data['log_code'] ?? 0);

        ob_clean();
        echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    } else {
        ob_clean();
        echo json_encode([
            "val_status" => "not_found", 
            "log_code" => 404,
            "error" => "Command ID: $id not found"
        ]);
    }

} catch (Exception $e) {
    if (ob_get_length()) ob_clean();
    http_response_code(500);
    echo json_encode([
        "val_status" => "error", 
        "log_code" => 500,
        "error" => "Database Error: " . $e->getMessage()
    ], JSON_UNESCAPED_UNICODE);
}

ob_end_flush();