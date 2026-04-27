<?php
// web/camviewer-test2.php
// WILDLINK RACK-CONSOLE (WES 2026) - V17.5 Architecture
$sys_id = isset($_GET['sys_id']) ? htmlspecialchars($_GET['sys_id'], ENT_QUOTES, 'UTF-8') : 'node_001';
?>
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WILDLINK 2026 | Rack Console Test</title>
    <link rel="stylesheet" href="css/vst-rack-test2.css">
</head>
<body>
    <header class="rack-header">
        <div class="rack-title">WILDLINK RACK-CONSOLE <span class="version">Ver 2026.1</span></div>
        <div class="rack-stats">CPU: 42.5°C &nbsp;&nbsp; RSSI: -65 dBm &nbsp;&nbsp; UP: 12:34:56</div>
    </header>

    <main class="rack-container" id="rack-main">
        <div id="content-sns_move" class="vst-plugin-container"></div>
    </main>

    <script src="js/vst-unit-base.js"></script>
    <script src="js/plugins/vst-unit-test2.js"></script>

    <script>
        document.addEventListener('DOMContentLoaded', () => {
            // マネージャーのモック
            const mockManager = { nodeId: '<?php echo $sys_id; ?>' };

            // DBから取得したと仮定する初期構成データ
            const mockConfig = {
                sys_id: '<?php echo $sys_id; ?>',
                vst_role_name: 'sns_move',
                val_name: 'TEST_MODULE_01',
                loc_name: 'SERVER_RACK_A',
                vst_description: '人感センサー（前方監視）',
                val_enabled: 1,
                val_status: 'IDLE',
                log_msg: 'SYSTEM READY.',
                log_code: 200,
                val_params: {
                    val_interval: 15,
                    val_alert_sync: 1,
                    val_alert_int: 15,
                    act_rec: 1,
                    act_db: 1,
                    act_line: 1,
                    act_rec_mode: 0 // 0: SNAP, 1: VIDEO
                }
            };

            // ユニット生成
            const testUnit = new VstUnitTest2(mockConfig, mockManager);
            
            // 3秒後にテストでアラートを発火（動作確認用）
            setTimeout(() => {
                testUnit.triggerAlert('YELLOW', 'SYNCING...');
                setTimeout(() => {
                    testUnit.updateFaceVisual({ log_msg: "MOTION DETECTED!", log_code: 302 });
                    testUnit.triggerAlert('RED', 'MOTION DETECTED');
                }, 3000);
            }, 2000);
        });
    </script>
</body>
</html>