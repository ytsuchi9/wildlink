<?php
/**
 * =========================================================
 * WildLink Event Standard (WES) 2026 準拠
 * コンポーネント: [UI/API] api/send_cmd.php
 * * 【フェーズ2: イベント駆動アーキテクチャへの対応】
 * 役割: ブラウザから受け取った操作要求をDBに記録(pending)し、
 * Hub(ハブマネージャー)へ「更新の合図(kick)」のみを送る。
 * * 責務の厳格化:
 * - このスクリプトは直接Nodeへコマンドを送信(mosquitto_pub)しません。
 * - 二重送信を防ぐため、実際のコマンドパブリッシュとステータス管理('sent'への更新)は
 * すべてHub側の hub_manager.py が一元的に担当します。
 * =========================================================
 */

header('Content-Type: application/json; charset=utf-8');

// 共通コアモジュールを読み込み
require_once dirname(__DIR__) . '/wildlink_core.php'; 

// 1. ブラウザ(JS)からのPOSTパラメータを安全に受け取る
$sys_id   = isset($_POST['sys_id']) ? trim($_POST['sys_id']) : '';
$cmd_type = isset($_POST['cmd_type']) ? trim($_POST['cmd_type']) : '';
$cmd_json = isset($_POST['cmd_json']) ? trim($_POST['cmd_json']) : '{}';

// 必須パラメータのチェック
if (empty($sys_id) || empty($cmd_json)) {
    echo json_encode(["val_status" => "error", "message" => "sys_id or cmd_json is missing."]);
    exit;
}

try {
    // 2. 送信された JSON を連想配列にパース
    $payload_data = json_decode($cmd_json, true);
    if (json_last_error() !== JSON_ERROR_NONE) {
        throw new Exception("Invalid JSON format in cmd_json.");
    }

    // 💡 WES 2026: トピック階層化とDB紐付けのための 'role' を抽出
    $target_role = isset($payload_data['role']) ? $payload_data['role'] : 'system';

    // 3. データベース (node_commandsテーブル) へコマンドを登録 (ステータスは pending のまま)
    $stmt = $pdo->prepare("
        INSERT INTO node_commands (sys_id, vst_role_name, cmd_type, cmd_json, val_status, created_at) 
        VALUES (:sys_id, :vst_role_name, :cmd_type, :cmd_json, 'pending', NOW())
    ");
    $stmt->bindValue(':sys_id', $sys_id, PDO::PARAM_STR);
    $stmt->bindValue(':vst_role_name', $target_role, PDO::PARAM_STR);
    $stmt->bindValue(':cmd_type', $cmd_type, PDO::PARAM_STR);
    $stmt->bindValue(':cmd_json', $cmd_json, PDO::PARAM_STR);
    $stmt->execute();
    
    // 発行された一意のコマンドID（cmd_id）を取得
    $cmd_id = $pdo->lastInsertId();

    // 4. MQTTでHubへ「キック(合図)」を送信する
    // 🌟【修正ポイント】: 直接Node宛のトピック(wildlink/...)には送らず、
    // Hubの目覚まし用トピック(system/hub/kick)に通知だけを送る。
    $kick_topic = "system/hub/kick";
    $kick_payload = json_encode([
        "event" => "new_command_pending",
        "cmd_id" => (int)$cmd_id,
        "sys_id" => $sys_id
    ]);

    // ※ .env等の構成によっては動的に読むのがベストですが、UIとHubが同居している前提で127.0.0.1
    $broker_host = "127.0.0.1";
    $escaped_topic = escapeshellarg($kick_topic);
    $escaped_payload = escapeshellarg($kick_payload);
    
    $exec_cmd = "mosquitto_pub -h {$broker_host} -t {$escaped_topic} -m {$escaped_payload}";
    exec($exec_cmd, $output, $return_var);

    // 送信失敗時のエラーハンドリング
    if ($return_var !== 0) {
        $err_stmt = $pdo->prepare("UPDATE node_commands SET val_status = 'error', log_msg = 'Hub kick failed' WHERE id = :id");
        $err_stmt->bindValue(':id', $cmd_id, PDO::PARAM_INT);
        $err_stmt->execute();
        
        throw new Exception("MQTT Broker unreachable or Hub kick failed.");
    }

    // 🌟【修正ポイント】: 以前あった 'sent' への UPDATE 処理を削除。
    // 'sent' への更新は、通知を受け取った hub_manager.py が実際にNodeへ送信した「直後」に行います。

    // 5. ブラウザへ成功レスポンスを返す
    echo json_encode([
        "val_status" => "success",
        "command_id" => (int)$cmd_id,
        "message" => "Command registered and Hub kicked.",
        "dispatched_topic" => $kick_topic
    ]);

} catch (Exception $e) {
    error_log("[WildLink send_cmd] Error: " . $e->getMessage());
    echo json_encode([
        "val_status" => "error", 
        "message" => $e->getMessage()
    ]);
}