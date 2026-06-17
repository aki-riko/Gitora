// 提交详情对话框(阶段 4:迁移 commit_detail_dialog.py)
// 只读展示:提交信息 + 变更文件列表 + 完整 diff
import QtQuick
import QtQuick.Layouts

import FluentQML as Fluent

Fluent.MessageBox {
    id: dlg
    title: "提交详情"
    confirmText: "关闭"
    cancelButtonVisible: false

    property string commitHash: ""
    ListModel { id: filesModel }

    function openFor(hash) {
        dlg.commitHash = hash
        var d = GitBridge.getCommitDetail(hash)
        msgLabel.text = d.message || ""
        metaLabel.text = (d.shortHash || "") + "  ·  " + (d.author || "") + "  ·  " + (d.date || "")
        filesModel.clear()
        var files = GitBridge.getCommitFiles(hash)
        for (var i = 0; i < files.length; i++) filesModel.append(files[i])
        diffArea.text = GitBridge.getCommitDiff(hash)
        dlg.open()
    }

    ColumnLayout {
        width: 560
        spacing: Fluent.Enums.spacing.m

        Text {
            id: msgLabel
            Layout.fillWidth: true
            color: Fluent.Enums.textColor.primary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.subtitle
            font.bold: true
            wrapMode: Text.WordWrap
        }
        Text {
            id: metaLabel
            Layout.fillWidth: true
            color: Fluent.Enums.textColor.tertiary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.caption
        }

        Text {
            text: "变更文件 (" + filesModel.count + ")"
            color: Fluent.Enums.textColor.secondary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.body
            font.bold: true
        }
        ListView {
            id: filesList
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(filesModel.count * 22 + 4, 120)
            clip: true
            model: filesModel
            delegate: RowLayout {
                width: filesList.width
                spacing: Fluent.Enums.spacing.m
                Text {
                    text: model.statusText
                    Layout.preferredWidth: 50
                    color: Fluent.Enums.textColor.tertiary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.caption
                }
                Text {
                    Layout.fillWidth: true
                    text: model.path
                    color: Fluent.Enums.textColor.primary
                    font.family: "Consolas, monospace"
                    font.pixelSize: Fluent.Enums.typography.caption
                    elide: Text.ElideMiddle
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 240
            radius: Fluent.Enums.radius.medium
            color: Fluent.Enums.cardColor
            border.width: Fluent.Enums.border.normal
            border.color: Fluent.Enums.stateColor.border
            Flickable {
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.s
                clip: true
                contentWidth: diffArea.paintedWidth
                contentHeight: diffArea.paintedHeight
                TextEdit {
                    id: diffArea
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.NoWrap
                    font.family: "Consolas, monospace"
                    font.pixelSize: Fluent.Enums.typography.caption
                    color: Fluent.Enums.textColor.primary
                }
            }
        }
    }
}
