// 冲突内容查看对话框(阶段 5:迁移 conflict_viewer_dialog.py)
// 只读展示冲突文件内容,对冲突标记行高亮:
//   <<<<<<< 蓝(我们的)  ======= 橙(分隔)  >>>>>>> 绿(他们的)
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.MessageBox {
    id: dlg
    title: "冲突内容"
    confirmText: "关闭"
    cancelButtonVisible: false

    ListModel { id: lineModel }

    function openFor(path) {
        dlg.title = "冲突内容 - " + path
        lineModel.clear()
        var content = GitBridge.readConflictFile(path) || ""
        if (content !== "") {
            var lines = content.split("\n")
            for (var i = 0; i < lines.length; i++)
                lineModel.append({ "line": lines[i] })
        }
        dlg.open()
    }

    function _lineColor(line) {
        if (line.indexOf("<<<<<<<") === 0) return Fluent.Enums.accentColor
        if (line.indexOf("=======") === 0) return Fluent.Enums.statusLevel.warningColor
        if (line.indexOf(">>>>>>>") === 0) return Fluent.Enums.statusLevel.successColor
        return Fluent.Enums.textColor.primary
    }

    ColumnLayout {
        width: 600
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 420
            radius: Fluent.Enums.radius.medium
            color: Fluent.Enums.cardColor
            border.width: Fluent.Enums.border.normal
            border.color: Fluent.Enums.stateColor.border

            ListView {
                id: lineList
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.s
                clip: true
                model: lineModel
                delegate: Text {
                    width: lineList.width
                    text: model.line
                    color: dlg._lineColor(model.line)
                    font.family: "Consolas, monospace"
                    font.pixelSize: Fluent.Enums.typography.caption
                    textFormat: Text.PlainText
                    wrapMode: Text.NoWrap
                }
            }
        }
    }
}
