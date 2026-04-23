<?php
// .env から MQTT_PREFIX を取得
// 🌟 自作の Core を読み込む
require_once 'wildlink_core.php';

// 🌟 getenv ではなく $core->getEnv を使う
$mqttPrefix = $core->getEnv('MQTT_PREFIX', 'wildlink');
?>

<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>WildLink 2026 | Rack Console</title>
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <link rel="stylesheet" href="css/vst-rack.css">
</head>
<body>
    <header>
        <h1>WILDLINK RACK-CONSOLE <small>Ver 2026.1</small></h1>
        <div id="system-vital-bar" class="vital-unit">
            <div class="vital-item">CPU: <span id="vital-cpu">--</span></div>
            <div class="vital-item">RSSI: <span id="vital-rssi">--</span></div>
            <div class="vital-item">UP: <span id="vital-up">--</span></div>
        </div>
    </header>

    <main id="vst-rack">
        </main>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/paho-mqtt/1.0.1/mqttws31.min.js"></script>
        <script src="js/plugins/vst-unit-base.js"></script>
        <script src="js/vst-manager.js"></script>

        <script>
            window.WES_CONFIG = {
                MQTT_PREFIX: "<?= $mqttPrefix ?>",
                DEFAULT_GROUP: "home_internal" 
            };

        const urlParams = new URLSearchParams(window.location.search);
        const sys_ID = urlParams.get('sys_id');
        const group_ID = urlParams.get('group_id') || window.WES_CONFIG.DEFAULT_GROUP;

        if (!sys_ID) {
            document.body.innerHTML = "<h2 style='color:red; text-align:center;'>ERROR: sys_id is missing.</h2>";
        } else {
            window.addEventListener('DOMContentLoaded', async () => {
                // 🌟 マネージャーの初期化（第3引数にプレフィックスを渡せるようにします）
                window.vstManagerInstance = new VstManager(sys_ID, group_ID, window.WES_CONFIG.MQTT_PREFIX);
                await window.vstManagerInstance.init();
            });
        }
    </script>
</body>
</html>