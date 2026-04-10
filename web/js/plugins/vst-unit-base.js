/**
 * WildLink 2026 - Unit Base Class
* VstUnitBase: 全プラグインの共通基盤 (JavaScript用)
 */
class VstUnitBase {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        this.role = conf.vst_role_name;
    }

    // 共通のUI初期化メソッド（各プラグインで中身を書く）
    initUI() {
        console.log(`[${this.role}] initUI`);
    }

    // 共通のデータ更新メソッド
    update(data) {
        this.onUpdate(data);
    }

    onUpdate(data) {
        // 各プラグインで上書きする
    }

    onEvent(data) {
        // 各プラグインで上書きする
    }
}

// 🌟 これで window.VstUnitBase が定義され、エラーが消えます
window.VstUnitBase = VstUnitBase;