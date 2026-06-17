// 危险操作确认对话框(阶段 4:迁移 danger_dialog.py 的倒计时机制)
// 利用 MessageBox 的 validate() 扩展点:倒计时未结束时 validate 返回 false,
// 确认按钮点了也不会关闭对话框。
//
// 用法:
//   DangerDialog { id: dlg; title:"..."; content:"..."; countdown: 3; onConfirmed: {...} }
//   dlg.start()   // 启动倒计时并打开
import QtQuick

import FluentQML as Fluent

Fluent.MessageBox {
    id: dlg

    property int countdown: 3
    property int _remaining: 0
    signal confirmed()

    confirmText: _remaining > 0 ? ("请等待 (" + _remaining + "s)") : "确认执行"
    cancelText: "取消"

    // 倒计时期间禁止确认(validate 返回 false 则确认按钮不触发 accept)
    function validate() {
        return dlg._remaining <= 0
    }

    onAccepted: dlg.confirmed()

    Timer {
        id: countdownTimer
        interval: 1000
        repeat: true
        onTriggered: {
            dlg._remaining--
            if (dlg._remaining <= 0) stop()
        }
    }

    // 启动倒计时并打开对话框
    function start() {
        _remaining = countdown
        if (countdown > 0) countdownTimer.restart()
        else countdownTimer.stop()
        dlg.open()
    }
}
