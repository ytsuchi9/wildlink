<?php
// web/camviewer-test2.php
// WILDLINK RACK-CONSOLE (WES 2026) - V17.7 (4K Ready & Hardware Texture)
$sys_id = isset($_GET['sys_id']) ? htmlspecialchars($_GET['sys_id'], ENT_QUOTES, 'UTF-8') : 'node_001';
?>
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WILDLINK 2026 | Rack Console</title>
    <link rel="stylesheet" href="css/vst-rack-test2.css">
</head>
<body>
    <header class="rack-header">
        <div class="rack-title">WILDLINK RACK-CONSOLE <span class="version">Ver 2026.1</span></div>
        <div class="rack-stats">CPU: 42.5°C &nbsp;&nbsp; RSSI: -65 dBm &nbsp;&nbsp; UP: 12:34:56</div>
    </header>

    <main class="rack-container" id="rack-main">
        <div id="content-sns_move_1" class="vst-plugin-container"></div>
        <div id="content-sns_move_2" class="vst-plugin-container"></div>
        <div id="content-sns_move_3" class="vst-plugin-container"></div>
        <div id="content-sns_move_4" class="vst-plugin-container"></div>
    </main>

    <script src="js/vst-unit-base.js"></script>
    <script src="js/plugins/vst-unit-test2.js"></script>

    <script>
        document.addEventListener('DOMContentLoaded', () => {
            const mockManager = { nodeId: '<?php echo $sys_id; ?>' };
            const roles = ['sns_move_1', 'sns_move_2', 'sns_move_3', 'sns_move_4'];

            roles.forEach((role, index) => {
                const num = index + 1;
                const mockConfig = {
                    sys_id: '<?php echo $sys_id; ?>',
                    vst_role_name: role,
                    val_name: 'TEST_MODULE_0' + num,
                    loc_name: 'SERVER_RACK_' + String.fromCharCode(64 + num),
                    vst_description: '人感センサー（前方監視 ' + num + '）',
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
                        act_rec_mode: 0
                    }
                };

                const unit = new VstUnitTest2(mockConfig, mockManager);
                
                if (num === 2) {
                    setTimeout(() => {
                        unit.updateFaceVisual({
                            val_status: 'ALERT',
                            log_msg: "MOTION DETECTED!", 
                            log_code: 302,
                            val_params: mockConfig.val_params
                        });
                        unit.triggerAlert('RED', 'MOTION DETECTED');
                    }, 3000);
                }
            });
        });
    </script>
</body>
</html>