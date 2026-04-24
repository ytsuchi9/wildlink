/**
 * js/plugins/switch-unit.js
 */
class SwitchUnit {
    constructor(conf, manager) {
        this.conf = conf;
        this.manager = manager;
        this.roleName = conf.vst_role_name;
    }

    initUI() {
        const controls = document.getElementById(`controls-${this.roleName}`);
        if (!controls) return;

        // スイッチ用のON/OFFボタンを生成
        controls.innerHTML = `
            <button onclick="vstManagerInstance.units['${this.roleName}'].instance.toggle(true)" class="vst-btn btn-on">ON</button>
            <button onclick="vstManagerInstance.units['${this.roleName}'].instance.toggle(false)" class="vst-btn btn-off">OFF</button>
        `;
    }

    async toggle(state) {
        const action = state ? 'start' : 'stop';
        const cmd = { role: this.roleName, action: action, act_run: state };
        
        // send_cmd.php 経由で命令を飛ばす (CameraUnitと同様のロジック)
        const fd = new FormData();
        fd.append('sys_id', this.manager.nodeId);
        fd.append('cmd_json', JSON.stringify(cmd));

        try {
            const res = await fetch('api/send_cmd.php', { method: 'POST', body: fd });
            const result = await res.json();
            if (result.success) console.log(`${this.roleName} -> ${action} queued.`);
        } catch (e) { console.error("Switch error:", e); }
    }

    update(unitData) {
        const disp = document.getElementById(`disp-${this.roleName}`);
        if (disp) disp.innerText = (unitData.val_status || "OFFLINE").toUpperCase();
    }
}

// 💡 忘れずに登録
window.SwitchUnit = SwitchUnit;