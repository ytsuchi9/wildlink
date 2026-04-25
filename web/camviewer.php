<?php
// 🌟 自作の Core を読み込む
require_once 'wildlink_core.php';

// getenv ではなく $core->getEnv を使う
$mqttPrefix = $core->getEnv('MQTT_PREFIX', 'wildlink');
?>

<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WildLink 2026 | Rack Console</title>
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <link rel="stylesheet" href="css/vst-rack.css">

    <style>
        /* 🌟 V17 Rack System Core Styles */
        :root {
            --accent-green: #00ff41;
            --accent-red: #ff3333;
            --accent-yellow: #ffc107;
            --accent-orange: #ff8c00;
            --text-dim: #555555;
        }
        body {
            background-color: #050505;
            color: #ccc;
            font-family: 'Share Tech Mono', monospace;
            margin: 0;
            padding: 0;
        }
        
        /* 💡 ラック全体の中央寄せと最大幅の制限 */
        #vst-rack {
            width: 100%;
            max-width: 800px;
            margin: 0 auto;
            padding: 10px;
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        /* 💡 V17の最大のキモ: 子要素(プラグイン)で 'cqi' 単位を使えるようにする */
        .vst-plugin {
            container-type: inline-size;
            width: 100%;
        }

        /* Managerが自動生成する旧型の見出しをCSSで強制非表示 (UIをV17に完全統一) */
        .vst-plugin .plugin-header {
            display: none !important;
        }

        /* ヘッダーの装飾 */
        header {
            background: #111;
            padding: 10px 15px;
            border-bottom: 2px solid #333;
            margin-bottom: 15px;
        }
        header h1 {
            margin: 0;
            font-size: 1.5rem;
            color: #fff;
        }
        .vital-unit {
            display: flex;
            gap: 15px;
            font-size: 0.9rem;
            color: #aaa;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <header>
        <h1>WILDLINK RACK-CONSOLE <small style="color:var(--accent-green); font-size: 0.8rem;">Ver 2026.1</small></h1>
        <div id="system-vital-bar" class="vital-unit">
            <div class="vital-item">CPU: <span id="vital-cpu" style="color: #fff;">--</span></div>
            <div class="vital-item">RSSI: <span id="vital-rssi" style="color: #fff;">--</span></div>
            <div class="vital-item">UP: <span id="vital-up" style="color: #fff;">--</span></div>
        </div>
    </header>

    <main id="vst-rack">
        </main>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/paho-mqtt/1.0.1/mqttws31.min.js"></script>
    <script src="js/vst-unit-base.js"></script>
    <script src="js/vst-manager.js"></script>

    <script>
        window.WES_CONFIG = {
            // XSS対策としてhtmlspecialcharsを通す
            MQTT_PREFIX: "<?= htmlspecialchars($mqttPrefix, ENT_QUOTES, 'UTF-8') ?>",
            DEFAULT_GROUP: "home_internal" 
        };

        const urlParams = new URLSearchParams(window.location.search);
        const sys_ID = urlParams.get('sys_id');
        const group_ID = urlParams.get('group_id') || window.WES_CONFIG.DEFAULT_GROUP;

        if (!sys_ID) {
            document.getElementById('vst-rack').innerHTML = "<h2 style='color:var(--accent-red); text-align:center; margin-top:2rem;'>ERROR: sys_id is missing.</h2>";
        } else {
            window.addEventListener('DOMContentLoaded', async () => {
                // マネージャーの初期化（プレフィックス対応）
                window.vstManagerInstance = new VstManager(sys_ID, group_ID, window.WES_CONFIG.MQTT_PREFIX);
                await window.vstManagerInstance.init();
            });
        }
    </script>
</body>
</html>