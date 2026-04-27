<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, shrink-to-fit=no, viewport-fit=cover">
    <title>VST UI SANDBOX</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="css/vst-rack-test.css">
</head>
<body style="background:#000; color:#fff;">

    <nav class="p-3 border-bottom border-secondary d-flex justify-content-between align-items-center">
        <h5 class="m-0">WES 2026 : RACK UI TESTER</h5>
        <button class="btn btn-outline-danger btn-sm" onclick="testAlert()">SIMULATE DETECTION</button>
    </nav>

    <div class="rack-container g-0 p-0" id="main-rack"></div>

    <script src="js/vst-unit-test.js"></script>
    <script>
        // グローバルにインスタンスを保持
        window.vstInstances = {};

        // テスト用に4つほど並べてみる
        const demoUnits = {
            'motion_f': '人感センサー (前方監視)',
            'motion_r': '人感センサー (後方監視)',
            'cam_main': 'RasPi Cam(Main)'
        };
        
        Object.keys(demoUnits).forEach(id => {
            const unit = new VstUnitTestBase(id, demoUnits[id]);
            unit.render('main-rack');
            window.vstInstances[id] = unit;
        });

        // 🌟 アラートシミュレーションボタン
        function testAlert() {
            if(window.vstInstances['motion_f']) {
                window.vstInstances['motion_f'].triggerAlert('red', 'MOTION DETECTED!');
            }
            if(window.vstInstances['motion_r']) {
                window.vstInstances['motion_r'].triggerAlert('yellow', 'SIGNAL WEAK');
            }
        }
    </script>
</body>
</html>