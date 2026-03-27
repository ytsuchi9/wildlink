<?php
/**
 * =========================================================
 * WildLink Event Standard (WES) 2026 準拠
 * 役割: ブラウザから受け取ったコマンドをDBに記録し、
 * 各デバイスの役割(Role)に合わせたMQTTトピックへ発行する
 * =========================================================
 */

header('Content-Type: application/json; charset=utf-8');

// 共通コアモジュール（DB接続や共通関数が含まれている想定）を読み込み
require_once '../wildlink_core.php'; 

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

    // 💡【重要変更】WES 2026: トピック階層化のための 'role' を抽出
    // 例: "cam_main", "sns_move", "log_sys" など。未指定なら安全のため "system" にする
    $target_role = isset($payload_data['role']) ? $payload_data['role'] : 'system';

    // 3. データベース (node_commandsテーブル) へコマンドを登録
    // ※ $pdo は wildlink_core.php で生成されたDB接続インスタンスと仮定
    $stmt = $pdo->prepare("
        INSERT INTO node_commands (sys_id, cmd_type, cmd_json, val_status, created_at) 
        VALUES (:sys_id, :cmd_type, :cmd_json, 'pending', NOW())
    ");
    $stmt->bindValue(':sys_id', $sys_id, PDO::PARAM_STR);
    $stmt->bindValue(':cmd_type', $cmd_type, PDO::PARAM_STR);
    $stmt->bindValue(':cmd_json', $cmd_json, PDO::PARAM_STR);
    $stmt->execute();
    
    // 発行された一意のコマンドID（cmd_id）を取得
    $cmd_id = $pdo->lastInsertId();

    // 4. MQTTペイロードの再構築 (WES 2026 準拠)
    // デバイス側が「どのコマンドに対する応答か」を返せるように cmd_id を付与する
    $payload_data['cmd_id'] = (int)$cmd_id;
    $mqtt_payload = json_encode($payload_data, JSON_UNESCAPED_UNICODE);

    // 💡【重要変更】WES 2026: 宛先トピックの動的生成 (Role-Based Routing)
    // 修正前: "vst/{sys_id}/cmd/vst_control"
    // 修正後: "nodes/{sys_id}/{role}/cmd"
    $mqtt_topic = "nodes/{$sys_id}/{$target_role}/cmd";

    // 5. MQTTブローカーへの Publish 処理
    // ※ mosquitto_pub コマンドをシェル経由で叩く一般的な実装例です。
    // ※ もし php-mqtt ライブラリ等をお使いの場合は、その記述に合わせてください。
    $broker_host = "127.0.0.1";
    $escaped_topic = escapeshellarg($mqtt_topic);
    $escaped_payload = escapeshellarg($mqtt_payload);
    
    // コマンド実行 (QoS 1 相当にする場合は -q 1 を追加)
    $exec_cmd = "mosquitto_pub -h {$broker_host} -t {$escaped_topic} -m {$escaped_payload}";
    exec($exec_cmd, $output, $return_var);

    // 送信失敗時のエラーハンドリング
    if ($return_var !== 0) {
        // DB上のステータスを 'error' に更新してあげる親切設計
        $err_stmt = $pdo->prepare("UPDATE node_commands SET val_status = 'error' WHERE id = :id");
        $err_stmt->bindValue(':id', $cmd_id, PDO::PARAM_INT);
        $err_stmt->execute();
        
        throw new Exception("MQTT Broker unreachable or publish failed.");
    }

    // 6. ブラウザ (vst-manager.js 等) へ成功レスポンスを返す
    // JS側はこの command_id を使って `get_command_status.php` をポーリングします
    echo json_encode([
        "val_status" => "success",
        "command_id" => $cmd_id,
        "dispatched_topic" => $mqtt_topic // デバッグ用に送信先トピックも含める
    ]);

} catch (Exception $e) {
    // 例外発生時のエラーレスポンス
    error_log("[WildLink send_cmd] Error: " . $e->getMessage());
    echo json_encode([
        "val_status" => "error", 
        "message" => $e->getMessage()
    ]);
}