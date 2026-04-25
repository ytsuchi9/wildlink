/**
 * VST Unit Master: High Visibility Edition (v17 - Mobile Fit)
 */
class VstUnitTestBase {
    constructor(dbInfo = {}) {
        this.db = Object.assign({
            vst_description: 'Unit', val_name: 'vst_0', sys_id: 'sys_0',
            val_enabled: true, val_status: 'IDLE', log_msg: 'Ready.'
        }, dbInfo);
        
        this.id = this.db.val_name;
        this.isExpanded = false;
        this.isKeep = false;
        this.isDirty = false;
        this.ui = {};
    }

    render(containerId) {
        const target = document.getElementById(containerId);
        const wrapper = document.createElement('div');
        wrapper.id = `vst-${this.id}`;
        wrapper.className = `vst-unit-box`;
        
        wrapper.innerHTML = `
            <div class="vst-unit-face">
                <div class="face-left">
                    <label class="power-switch-v"><input type="checkbox" class="ui-sw" ${this.db.val_enabled ? 'checked' : ''}><span class="slider"></span></label>
                    <button class="btn-vst apply-btn-mini ui-apply">APPLY</button>
                </div>
                <div class="face-center">
                    <div class="unit-header-bar ui-header">
                        <div style="font-size:3.5cqi;font-weight:bold;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;">${this.db.vst_description}</div>
                        <div style="font-family:monospace;font-size:1.8cqi;flex-shrink:0;opacity:0.8;">${this.db.sys_id}</div>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.4cqi;">
                        <div style="font-family:monospace;font-size:2.1cqi;color:#aaa;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;flex:1;">
                            <span style="color:#888;">STAT:</span><span class="ui-stat" style="color:var(--accent-green);margin-right:1cqi;">${this.db.val_status}</span>
                            <span class="ui-log">${this.db.log_msg}</span>
                        </div>
                        <div style="display:flex;align-items:center;gap:1cqi;flex-shrink:0;">
                            <div class="vst-meter-mini"><div class="vst-meter-fill ui-meter"></div></div>
                            <div class="vst-disp-mini ui-disp">0.0</div>
                        </div>
                    </div>
                </div>
                <div class="face-right">
                    <button class="icon-btn ui-exp" style="font-size:2.5cqi;">⛶</button>
                    <button class="icon-btn ui-keep" style="font-size:1.6cqi;">固定</button>
                </div>
            </div>
            <div class="unit-body">
                <div class="test-lcd ui-lcd">> SYSTEM READY.</div>
                <div class="settings-area">
                    <div style="font-size:2.2cqi;color:#888;">THRESHOLD <span style="color:var(--accent-orange);" class="ui-val-s">50</span></div>
                    <input type="range" class="vst-slider ui-slider" min="0" max="100" value="50">
                    <label style="display:flex;align-items:center;gap:0.8cqi;font-size:2.2cqi;color:#ccc;cursor:pointer;margin-top:1cqi;">
                        <input type="checkbox" class="ui-opt" checked> AUTO_LOG
                    </label>
                    <div style="display:flex;gap:0.5cqi;margin-top:auto;">
                        <button class="btn-vst action-btn ui-reset">RESET</button>
                        <button class="btn-vst action-btn ui-apply">APPLY</button>
                    </div>
                </div>
            </div>
        `;
        target.appendChild(wrapper);

        this.ui = {
            box: wrapper,
            header: wrapper.querySelector('.ui-header'),
            sw: wrapper.querySelector('.ui-sw'),
            applies: wrapper.querySelectorAll('.ui-apply'),
            reset: wrapper.querySelector('.ui-reset'),
            exp: wrapper.querySelector('.ui-exp'),
            keep: wrapper.querySelector('.ui-keep'),
            slider: wrapper.querySelector('.ui-slider'),
            sliderVal: wrapper.querySelector('.ui-val-s'),
            opt: wrapper.querySelector('.ui-opt'),
            stat: wrapper.querySelector('.ui-stat'),
            log: wrapper.querySelector('.ui-log'),
            lcd: wrapper.querySelector('.ui-lcd'),
            meter: wrapper.querySelector('.ui-meter'),
            disp: wrapper.querySelector('.ui-disp')
        };

        this.ui.sw.onchange = () => { this.db.val_enabled = this.ui.sw.checked; this.markDirty(); };
        this.ui.opt.onchange = () => this.markDirty();
        this.ui.slider.oninput = (e) => { this.ui.sliderVal.innerText = e.target.value; this.markDirty(); };
        this.ui.exp.onclick = () => this.toggle();
        this.ui.keep.onclick = () => this.toggleKeep();
        this.ui.reset.onclick = () => this.reset();
        this.ui.applies.forEach(btn => btn.onclick = () => this.apply());

        setInterval(() => {
            if(!this.db.val_enabled) return;
            const r = Math.random() * 100;
            this.ui.meter.style.width = r + '%';
            this.ui.disp.innerText = r.toFixed(1);
        }, 1500);
    }

    markDirty() {
        this.isDirty = true;
        this.ui.applies.forEach(btn => btn.classList.add('dirty'));
        this.ui.reset.classList.add('active');
    }

    reset() {
        if(!this.isDirty) return;
        if(!confirm("変更を破棄して元に戻しますか？")) return;
        this.isDirty = false;
        this.ui.applies.forEach(btn => btn.classList.remove('dirty'));
        this.ui.reset.classList.remove('active');
        this.updateStatus(this.db.val_status, "Settings reset.");
    }

    apply() {
        if(!this.isDirty) return;
        this.isDirty = false;
        this.updateStatus("SYNC", "Applying...");
        this.ui.applies.forEach(btn => { btn.classList.remove('dirty'); btn.classList.add('success'); });
        setTimeout(() => {
            this.ui.applies.forEach(btn => btn.classList.remove('success'));
            this.ui.reset.classList.remove('active');
            this.updateStatus("ACTIVE", "Applied.");
        }, 800);
    }

    toggle() {
        if (this.isKeep && this.isExpanded) return;
        this.isExpanded = !this.isExpanded;
        this.ui.box.classList.toggle('expanded', this.isExpanded);
        this.ui.exp.innerText = this.isExpanded ? '▲' : '⛶';
        this.ui.exp.classList.toggle('active', this.isExpanded);
    }

    toggleKeep() {
        this.isKeep = !this.isKeep;
        this.ui.keep.classList.toggle('active', this.isKeep);
        if (this.isKeep && !this.isExpanded) this.toggle();
    }

    updateStatus(stat, msg) {
        if(this.ui.stat) this.ui.stat.innerText = stat;
        if(this.ui.log) this.ui.log.innerText = msg;
        if(this.ui.lcd) {
            const t = new Date().toLocaleTimeString('ja-JP',{hour12:false});
            this.ui.lcd.innerHTML += `<br><span style="color:#555;">[${t}]</span> ${msg}`;
            this.ui.lcd.scrollTop = this.ui.lcd.scrollHeight;
        }
    }

    // 🌟 アラート: タイトルバー全体の色を変えて点滅させる
    triggerAlert(level, msg = "ALERT") {
        const lvl = level.toUpperCase();
        this.ui.box.classList.remove('alert-header-red', 'alert-header-yellow');
        
        if(lvl === 'RED') {
            this.ui.box.classList.add('alert-header-red');
            this.updateStatus("ALARM", msg);
            if(!this.isExpanded) this.toggle();
        } else if(lvl === 'YELLOW') {
            this.ui.box.classList.add('alert-header-yellow');
            this.updateStatus("WARN", msg);
        }
    }
}

// 初期化 (変更なし)
window.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('vst-container');
    if(!container) return;
    window.vstInstances = {};
    const units = [
        { vst_description: '人感センサー (前方監視)', val_name: 'motion_f', sys_id: 'sys_001' },
        { vst_description: 'RasPi Cam (Main)', val_name: 'cam_main', sys_id: 'sys_002' }
    ];
    units.forEach(u => {
        const ins = new VstUnitTestBase(u);
        window.vstInstances[u.val_name] = ins;
        ins.render('vst-container');
    });
});