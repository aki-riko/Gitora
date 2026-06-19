// 全盘扫描 Git 仓库对话框
// 连 RepoScanner(后台 os.walk),实时累积结果,点击仓库即打开
import QtQuick
import QtQuick.Layouts

import FluentQML as Fluent

Fluent.MessageBox {
    id: dlg
    title: "扫描 Git 仓库"
    confirmText: "关闭"
    cancelButtonVisible: false

    signal repoChosen(string path)
    ListModel { id: foundModel }
    property bool scanning: false

    function startScan() {
        foundModel.clear()
        dlg.scanning = true
        dlg.open()
        RepoScanner.start()   // 默认扫所有固定磁盘
    }

    Connections {
        target: typeof RepoScanner !== "undefined" ? RepoScanner : null
        function onRepoFound(path) { foundModel.append({ "path": path }) }
        function onScanFinished(count) { dlg.scanning = false }
        function onScanningChanged(s) { dlg.scanning = s }
    }

    ColumnLayout {
        width: 560
        spacing: Fluent.Enums.spacing.m

        // 状态行
        RowLayout {
            Layout.fillWidth: true
            spacing: Fluent.Enums.spacing.m
            Fluent.ProgressRing {
                visible: dlg.scanning
                indeterminate: true
                implicitWidth: 20; implicitHeight: 20
            }
            Text {
                Layout.fillWidth: true
                text: dlg.scanning ? ("正在扫描... 已找到 " + foundModel.count + " 个")
                                   : ("扫描完成,共 " + foundModel.count + " 个仓库")
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.body
            }
            Fluent.Button {
                text: "停止"
                style: Fluent.Enums.button.style_transparent
                visible: dlg.scanning
                onClicked: RepoScanner.stop()
            }
        }

        // 结果列表
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 360
            radius: Fluent.Enums.radius.medium
            color: Fluent.Enums.cardColor
            border.width: Fluent.Enums.border.normal
            border.color: Fluent.Enums.stateColor.border

            Fluent.ListView {
                id: resultList
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.xs
                framed: false
                model: foundModel
                delegate: Rectangle {
                    width: resultList.listView ? resultList.listView.width : 0
                    height: 36
                    radius: Fluent.Enums.radius.small
                    color: rowHover.hovered ? Fluent.Enums.stateColor.hover : "transparent"
                    HoverHandler { id: rowHover }
                    TapHandler {
                        onTapped: {
                            dlg.repoChosen(model.path)
                            dlg.accept()
                        }
                    }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Fluent.Enums.spacing.m
                        anchors.rightMargin: Fluent.Enums.spacing.m
                        spacing: Fluent.Enums.spacing.m
                        Fluent.Icon {
                            icon: Fluent.Enums.icon.folder
                            iconSize: Fluent.Enums.iconSize.s
                            color: Fluent.Enums.accentColor
                        }
                        Text {
                            Layout.fillWidth: true
                            text: model.path
                            color: Fluent.Enums.textColor.primary
                            font.family: Fluent.Enums.fontFamily
                            font.pixelSize: Fluent.Enums.typography.body
                            elide: Text.ElideMiddle
                        }
                    }
                }
            }
        }
    }
}
