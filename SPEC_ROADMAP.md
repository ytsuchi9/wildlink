SPEC_ROADMAP.md
1. プロジェクト概要
WildLink: 野生環境下での長期運用を想定した、プラグイン方式（VST）の自律型監視・計測システム。

2. 開発フェーズ
Phase 1: Stabilization (現状)
目標: 配信制御の完全な安定化。
内容:
/etc/fstab (sshfs) による Pi2 - PiZero 間の開発環境同期の確立。
MQTT + MySQL 連携による、Webからの配信開始/停止（stream_start/stop）の実装。
最新命名規則（hw_, val_, act_, env_, sys_, log_, net_, loc_）のコードへの完全適用。

Phase 2: Adaptive Streaming (適応型配信)
目標: ハードウェア・通信環境に応じた柔軟な映像伝送。
内容:
VST Camera 分隊化: vst_cam_hw (PiZeroハードウェアエンコード) と vst_cam_sw の選択。
プロトコル・スウィッチャー: val_params により UDP (低遅延) と TCP (確実性) を動的に切り替え。
ネットワーク適応: 通信状況悪化時にビットレートの自動低下やステータステロップを表示。

Phase 3: Autonomous & Survival (自律・生存優先モード)
目標: 外部電源や物理的衝撃に対する自律的な判断と通知。
内容:
生存優先モード: ソーラー運用時、電圧（sys_volt）低下を検知したら映像を遮断。環境データ（env_）の計測継続を最優先する。
衝撃検知アラート: 加速度センサーVSTを実装。強い衝撃（act_impact）検知時に、LINEユニットと連携して通知＋証拠写真の即時ストリーミング。

3. 共通データ構造 (命名規則抜粋)
sys_status: システム全体の稼働状態
val_status: 各VSTユニットの個別動作状態
sys_volt: バッテリー/電源電圧
log_msg: デバッグおよび運用ログ




