<?php
// /var/www/html/upload.php
// /var/www/html/upload.php の冒頭に追加
file_put_contents('upload_debug.log', print_r($_FILES, true), FILE_APPEND);


// 1. 保存先ディレクトリの準備
$uploadDir = 'camimages/';
if (!is_dir($uploadDir)) {
    mkdir($uploadDir, 0777, true);
}

// 2. ファイルの受け取り
if (isset($_FILES['file'])) {
    $file = $_FILES['file'];
    $filename = basename($file['name']); // 例: cam1_20260118_123456.mp4
    $targetPath = $uploadDir . $filename;

    // ファイル移動
    if (move_uploaded_file($file['tmp_name'], $targetPath)) {
        echo "Upload Success: " . $filename;
        
        // ログにも記録しておく（mqtt_logger.pyと足並みを揃える）
        system_log("Video Received and Saved: " . $filename);
    } else {
        header("HTTP/1.1 500 Internal Server Error");
        echo "Error: Could not move uploaded file.";
    }
} else {
    header("HTTP/1.1 400 Bad Request");
    echo "Error: No file uploaded.";
}

// 簡易ログ記録関数 (master_config.jsonのパスを流用)
function system_log($message) {
    $config = json_decode(file_get_contents('master_config.json'), true);
    $logPath = $config['system']['log_path'];
    $timestamp = date('Y-m-d H:i:s');
    file_put_contents($logPath, "[$timestamp] [UPLOAD] $message\n", FILE_APPEND);
}
?>