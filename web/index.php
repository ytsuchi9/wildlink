<?php
/**
 * 監視カメラアーカイブシステム - プロ仕様 最終統合版
 * * 主な機能:
 * - タイムゾーン: Asia/Tokyo (日本時間) 固定
 * - グルーピング: 12:00(正午)を境にした「一晩単位」の活動表示
 * - 安全性: 録画中のファイル破損を避ける10秒バッファ
 * - 操作性: 動画中央プレイボタン、動画終了時の送りボタン自動復帰
 * - 管理: ブロック別一括選択・削除機能
 */

// --- 1. 基本設定とディレクトリ準備 ---
date_default_timezone_set('Asia/Tokyo'); 
$dir = "camimages/";
$thumbDir = "camimages/thumbs/";

if (!is_dir($thumbDir)) {
    mkdir($thumbDir, 0775, true);
}

// --- 2. 削除処理 (POSTリクエスト時) ---
if (isset($_POST['delete_files']) && !empty($_POST['selected_items'])) {
    foreach ($_POST['selected_items'] as $file_to_delete) {
        $real_path = realpath($file_to_delete);
        $base_path = realpath($dir);
        
        // camimagesディレクトリ内のファイルのみ削除を許可するセキュリティチェック
        if ($real_path && strpos($real_path, $base_path) === 0 && is_file($file_to_delete)) {
            unlink($file_to_delete);
            // サムネイルもセットで削除
            $thumb_file = $thumbDir . pathinfo($file_to_delete, PATHINFO_FILENAME) . ".jpg";
            if (file_exists($thumb_file)) unlink($thumb_file);
        }
    }
    // 削除後にページをリフレッシュ（二重送信防止）
    header("Location: " . $_SERVER['PHP_SELF']);
    exit;
}

// --- 3. ファイル一覧の取得とフィルタリング ---
$allFiles = glob($dir . "*.{jpg,jpeg,png,mp4,webm}", GLOB_BRACE);
$files = array_filter($allFiles, function($f) {
    // SSD書き込み中や転送中のファイルを避けるため、更新から10秒経過したもののみ表示
    return is_file($f) && filemtime($f) < (time() - 10);
});

// 新しい順（降順）にソート
usort($files, function($a, $b) {
    return filemtime($b) - filemtime($a);
});

/**
 * 動画の1コマ目からサムネイルを生成する関数
 */
function getThumb($file, $thumbDir) {
    $ext = strtolower(pathinfo($file, PATHINFO_EXTENSION));
    if (in_array($ext, ['mp4', 'webm'])) {
        $thumbFile = $thumbDir . pathinfo($file, PATHINFO_FILENAME) . ".jpg";
        if (!file_exists($thumbFile)) {
            // ffmpegで抽出（サイズは320x180）
            shell_exec("ffmpeg -i " . escapeshellarg($file) . " -ss 00:00:01 -vframes 1 -s 320x180 " . escapeshellarg($thumbFile));
        }
        return $thumbFile;
    }
    return $file; // 静止画はそのまま
}
?>

<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>監視アーカイブ Pro</title>
    
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/lightgallery/2.7.2/css/lightgallery-bundle.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/lightgallery/2.7.2/css/lg-video.min.css">
    
    <style>
        /* 基本テーマ設定 */
        body { font-family: -apple-system, sans-serif; margin: 0; background: #1a1a1a; color: #fff; padding-bottom: 90px; }
        
        /* ヘッダー: 固定表示 */
        header { 
            background: #222; padding: 15px; position: sticky; top: 0; z-index: 1000; 
            border-bottom: 1px solid #444; display: flex; justify-content: space-between; align-items: center; 
        }
        
        /* 日付見出し: 12時区切り */
        .date-divider { 
            background: #333; padding: 10px 15px; margin: 20px 0 10px 0; 
            border-left: 5px solid #007bff; font-size: 0.9rem; 
            display: flex; justify-content: space-between; align-items: center; 
        }
        .block-select-btn { background: #444; border: 1px solid #666; color: #eee; padding: 5px 12px; border-radius: 4px; font-size: 0.75rem; cursor: pointer; }

        /* グリッド表示 */
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; padding: 10px; }
        .item-box { background: #2a2a2a; border-radius: 8px; overflow: hidden; position: relative; border: 1px solid #333; transition: 0.2s; }
        .item-box:hover { border-color: #555; }
        
        /* サムネイル */
        .item { cursor: pointer; position: relative; aspect-ratio: 16/9; overflow: hidden; background: #000; display: block; }
        .item img { width: 100%; height: 100%; object-fit: cover; }
        
        /* 中央プレイボタン */
        .video-icon::after {
            content: "▶"; position: absolute; top: 50%; left: 50%;
            transform: translate(-50%, -50%); background: rgba(0,0,0,0.6);
            color: #fff; border: 2px solid #fff; border-radius: 50%; 
            width: 54px; height: 54px; display: flex; align-items: center; justify-content: center;
            font-size: 26px; text-indent: 4px; z-index: 2; pointer-events: none;
        }

        /* 下部ラベル */
        .time-label { font-size: 11px; padding: 8px; color: #bbb; display: flex; justify-content: space-between; align-items: center; }
        .delete-check { transform: scale(1.5); cursor: pointer; }

        /* 削除ボタンエリア */
        .footer-bar { 
            position: fixed; bottom: 0; width: 100%; background: rgba(25,25,25,0.96); 
            padding: 15px; text-align: center; border-top: 1px solid #444; z-index: 2000; 
        }
        .btn-delete { background: #d9534f; color: white; border: none; padding: 12px 40px; border-radius: 5px; cursor: pointer; font-weight: bold; font-size: 1rem; box-shadow: 0 -2px 10px rgba(0,0,0,0.5); }
        
        /* --- ビュワー操作性の向上 --- */
        
        /* 再生中(lg-video-playing)は矢印とツールバーを隠して没入感を出す */
        .lg-video-playing .lg-prev, 
        .lg-video-playing .lg-next,
        .lg-video-playing .lg-toolbar { 
            opacity: 0; 
            visibility: hidden;
            transition: opacity 0.4s ease;
        }

        /* 全画面表示時に矢印が動画の下に隠れないようz-indexを強化 */
        .lg-outer .lg-prev, .lg-outer .lg-next {
            z-index: 1200 !important;
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 50%;
            margin: 0 10px;
        }
        .lg-outer .lg-prev:hover, .lg-outer .lg-next:hover { background-color: rgba(255, 255, 255, 0.2); }
    </style>
</head>
<body>

<form id="main-form" method="POST">
    <header>
        <h2>監視ログ (<?php echo count($files); ?>)</h2>
        <label style="cursor:pointer;"><input type="checkbox" id="check-all"> 全日程を選択</label>
    </header>

    <?php 
    $last_activity_day = "";
    $block_id = 0;
    
    foreach ($files as $file): 
        $mtime = filemtime($file);
        
        // 正午(12:00)区切り: 午前中のファイルは「前日の夜の活動」としてグループ化
        $activity_day = date("Y/m/d", $mtime - (12 * 3600)); 

        if ($last_activity_day !== $activity_day) {
            if ($last_activity_day !== "") echo '</div>'; 
            $block_id++;
            echo '<div class="date-divider">';
            echo '<span>' . $activity_day . ' の夜間活動 </span>';
            echo '<button type="button" class="block-select-btn" onclick="selectBlock('.$block_id.')">この日の分を選択</button>';
            echo '</div>';
            echo '<div class="grid" id="lightgallery-'.$block_id.'">';
            $last_activity_day = $activity_day;
        }

        $ext = strtolower(pathinfo($file, PATHINFO_EXTENSION));
        $is_video = in_array($ext, ['mp4', 'webm']);
        $displayThumb = getThumb($file, $thumbDir);
        $full_ts = date("Y/m/d H:i:s", $mtime);
    ?>
        <div class="item-box">
            <?php if ($is_video): ?>
                <a class="item video-icon" 
                   data-lg-size="1280-720" 
                   data-video='{"source": [{"src":"<?php echo $file; ?>", "type":"video/mp4"}], "attributes": {"preload": "auto", "controls": true, "playsinline": true}}' 
                   data-sub-html="<h4><?php echo $full_ts; ?></h4>">
                    <img src="<?php echo $displayThumb; ?>" loading="lazy" />
                </a>
            <?php else: ?>
                <a class="item" href="<?php echo $file; ?>" data-sub-html="<h4><?php echo $full_ts; ?></h4>">
                    <img src="<?php echo $displayThumb; ?>" loading="lazy" />
                </a>
            <?php endif; ?>
            
            <div class="time-label">
                <span><?php echo date("H:i:s", $mtime); ?></span>
                <input type="checkbox" name="selected_items[]" value="<?php echo $file; ?>" class="delete-check block-item-<?php echo $block_id; ?>">
            </div>
        </div>
    <?php endforeach; ?>
    </div>

    <div class="footer-bar">
        <button type="submit" name="delete_files" class="btn-delete" onclick="return confirm('選択したファイルを削除しますか？\n（サムネイルも同時に削除されます）');">選択したアイテムを削除</button>
    </div>
</form>

<script src="https://cdnjs.cloudflare.com/ajax/libs/lightgallery/2.7.2/lightgallery.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/lightgallery/2.7.2/plugins/video/lg-video.umd.min.js"></script>

<script>
    // LightGallery初期化
    document.querySelectorAll('[id^="lightgallery-"]').forEach(el => {
        const lg = lightGallery(el, {
            plugins: [lgVideo],
            selector: '.item',
            speed: 500,
            videojs: false, 
            autoplayVideoOnSlide: false,
            gotoNextSlideOnVideoEnd: false, // 要望: 再生終了時に勝手に飛ばない
            mobileSettings: { controls: true, showCloseIcon: true }
        });

        // 要望: 再生終了時に「次へ」ボタンを即座に再表示させるためのイベント
        el.addEventListener('lgAfterAppendSlide', (e) => {
            const videoElement = document.querySelector('.lg-video-object');
            if (videoElement) {
                // 動画が終了(ended)したら、外側のコンテナから「再生中」クラスを削除する
                videoElement.addEventListener('ended', () => {
                    const outer = document.querySelector('.lg-outer');
                    if (outer) outer.classList.remove('lg-video-playing');
                });
            }
        });
    });

    // 日付ブロック単位の選択機能
    function selectBlock(id) {
        const checks = document.querySelectorAll('.block-item-' + id);
        const allChecked = Array.from(checks).every(c => c.checked);
        checks.forEach(c => c.checked = !allChecked);
    }

    // 全日程の選択機能
    document.getElementById('check-all').addEventListener('change', function() {
        document.querySelectorAll('.delete-check').forEach(cb => cb.checked = this.checked);
    });
</script>

</body>
</html>