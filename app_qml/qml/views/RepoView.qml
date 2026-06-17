// 仓库视图(阶段 0 验证页:打开仓库 + 显示变更列表,验证 GitBridge 数据流)
import QtQuick
import QtQuick.Dialogs

import FluentQML as Fluent

Item {
    id: root

    Column {
        anchors.fill: parent
        anchors.margins: Fluent.Enums.spacing.xl
        spacing: Fluent.Enums.spacing.l

        Text {
            text: "仓库"
            font.pixelSize: Fluent.Enums.typography.displayLarge
            font.bold: true
            color: Fluent.Enums.textColor.primary
            font.family: Fluent.Enums.fontFamily
        }

        Row {
            spacing: Fluent.Enums.spacing.m
            Fluent.Button {
                text: "打开仓库"
                icon: Fluent.Enums.icon.folder
                onClicked: folderDialog.open()
            }
            Fluent.Button {
                text: "刷新"
                onClicked: root.reload()
            }
        }

        Text {
            id: repoLabel
            text: (GitBridge && GitBridge.repoPath) ? ("当前仓库: " + GitBridge.repoPath) : "未打开仓库"
            color: Fluent.Enums.textColor.secondary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.body
        }

        ListView {
            id: changeList
            width: parent.width
            height: parent.height - y
            clip: true
            model: ListModel { id: changeModel }
            delegate: Item {
                width: changeList.width
                height: 36
                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Fluent.Enums.spacing.m
                    Text {
                        text: model.statusText
                        width: 60
                        color: model.staged ? Fluent.Enums.statusLevel.successColor : Fluent.Enums.textColor.tertiary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.caption
                    }
                    Text {
                        text: model.path
                        color: Fluent.Enums.textColor.primary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.body
                    }
                }
            }
        }
    }

    FolderDialog {
        id: folderDialog
        title: "选择 Git 仓库目录"
        onAccepted: {
            var path = selectedFolder.toString().replace(/^file:\/\/\//, "")
            if (GitBridge.setRepoPath(path)) {
                root.reload()
            } else {
                console.warn("不是有效的 Git 仓库: " + path)
            }
        }
    }

    function reload() {
        changeModel.clear()
        var list = GitBridge.getStatus()
        for (var i = 0; i < list.length; i++) {
            changeModel.append(list[i])
        }
    }

    Connections {
        target: GitBridge
        function onStatusChanged() { root.reload() }
    }
}
