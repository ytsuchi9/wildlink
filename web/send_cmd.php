<?php
// send_cmd.php
// WildLink Project: MQTT Command Dispatcher & Logger

require_once 'db_config.php';

// 1. パラメータ取得 (動的UI化への布石として ID を受け取れるようにする)
// cam_id が指定されない場合はデフォルトで node_001 を使用
$sys_id  = $_POST['cam_id']  ?? 'node_001';
$command = $_POST['command'] ?? '';

if (empty($command)) {
    die("Error: No command specified.");
}

// 2. コマンドの正規化 (規約 act_ に合わせた内部コマンド名)
// ブラウザからの 'start_motion' 等を 'cam_start' に変換
if ($command === 'start_motion' || $command === 'start') {
    $mqtt_msg = "cam_start";
} elseif ($command === 'stop_motion' || $command === 'stop') {
    $mqtt_msg = "cam_stop";
} else {
    $mqtt_msg = $command; // その他のコマンドはそのまま
}

// 3. MQTTパブリッシュ (シェル経由で mosquitto_pub を実行)
$topic = "wildlink/" . $sys_id . "/cmd";
$escaped_topic = escapeshellarg($topic);
$escaped_msg   = escapeshellarg($mqtt_msg);

// 送信実行
exec("mosquitto_pub -t $escaped_topic -m $escaped_msg 2>&1", $output, $return_var);

if ($return_var !== 0) {
    $mqtt_status = "MQTT Error: " . implode("\n", $output);
} else {
    $mqtt_status = "MQTT Success: Published '$mqtt_msg' to $topic";
}

// 4. データベースへの記録 (規約: sys_id, act_type)
$db_log_status = "";
$sql = "INSERT INTO command_logs (sys_id, act_type, status) VALUES (?, ?, 'sent')";
$stmt = $mysqli->prepare($sql);

if ($stmt) {
    $stmt->bind_param("ss", $sys_id, $mqtt_msg);
    if ($stmt->execute()) {
        $db_log_status = "DB Success: Command logged.";
    } else {
        $db_log_status = "DB Error: " . $stmt->error;
    }
    $stmt->close();
} else {
    $db_log_status = "DB Prepare Error: " . $mysqli->error;
}

$mysqli->close();

// 5. 結果をブラウザに返す
echo "<h3>WildLink Command Status</h3>";
echo "<ul>";
echo "<li><strong>Target ID:</strong> $sys_id</li>";
echo "<li><strong>Result:</strong> $mqtt_status</li>";
echo "<li><strong>Log:</strong> $db_log_status</li>";
echo "</ul>";
?>