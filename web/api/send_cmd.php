<?php
/**
 * =========================================================
 * WildLink Event Standard (WES) 2026 準拠
 * 役割: ブラウザから受け取ったコマンドをDBに記録し、
 * 各デバイスの役割(Role)に合わせたMQTTトピックへ発行する
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

    // 💡【修正ポイント】WES 2026: トピック階層化とDB紐付けのための 'role' を抽出
    $target_role = isset($payload_data['role']) ? $payload_data['role'] : 'system';

    // 3. データベース (node_commandsテーブル) へコマンドを登録
    // 💡【修正ポイント】vst_role_name カラムに $target_role を明示的に保存する
    $stmt = $pdo->prepare("
        INSERT INTO node_commands (sys_id, vst_role_name, cmd_type, cmd_json, val_status, created_at) 
        VALUES (:sys_id, :vst_role_name, :cmd_type, :cmd_json, 'pending', NOW())
    ");
    $stmt->bindValue(':sys_id', $sys_id, PDO::PARAM_STR);
    $stmt->bindValue(':vst_role_name', $target_role, PDO::PARAM_STR); // 👈 これが重要
    $stmt->bindValue(':cmd_type', $cmd_type, PDO::PARAM_STR);
    $stmt->bindValue(':cmd_json', $cmd_json, PDO::PARAM_STR);
    $stmt->execute();
    
    // 発行された一意のコマンドID（cmd_id）を取得
    $cmd_id = $pdo->lastInsertId();

    // 4. MQTTペイロードの再構築
    $payload_data['cmd_id'] = (int)$cmd_id;
    $mqtt_payload = json_encode($payload_data, JSON_UNESCAPED_UNICODE);

    // 💡 WES 2026: 宛先トピックの動的生成
    $mqtt_topic = "nodes/{$sys_id}/{$target_role}/cmd";

    // 5. MQTTブローカーへの Publish 処理
    $broker_host = "127.0.0.1";
    $escaped_topic = escapeshellarg($mqtt_topic);
    $escaped_payload = escapeshellarg($mqtt_payload);
    
    $exec_cmd = "mosquitto_pub -h {$broker_host} -t {$escaped_topic} -m {$escaped_payload}";
    exec($exec_cmd, $output, $return_var);

    // 送信失敗時のエラーハンドリング
    if ($return_var !== 0) {
        $err_stmt = $pdo->prepare("UPDATE node_commands SET val_status = 'error', log_msg = 'MQTT publish failed' WHERE id = :id");
        $err_stmt->bindValue(':id', $cmd_id, PDO::PARAM_INT);
        $err_stmt->execute();
        
        throw new Exception("MQTT Broker unreachable or publish failed.");
    }

    // DB上のステータスを 'sent' に更新 (送信成功を記録)
    $upd_stmt = $pdo->prepare("UPDATE node_commands SET val_status = 'sent', sent_at = NOW() WHERE id = :id");
    $upd_stmt->bindValue(':id', $cmd_id, PDO::PARAM_INT);
    $upd_stmt->execute();

    // 6. ブラウザへ成功レスポンスを返す
    echo json_encode([
        "val_status" => "success",
        "command_id" => (int)$cmd_id,
        "dispatched_topic" => $mqtt_topic
    ]);

} catch (Exception $e) {
    error_log("[WildLink send_cmd] Error: " . $e->getMessage());
    echo json_encode([
        "val_status" => "error", 
        "message" => $e->getMessage()
    ]);
}