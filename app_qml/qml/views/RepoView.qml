// 仓库视图(阶段 2:完整迁移 repo_interface.py)
// 布局:Header(仓库信息+操作) + SplitPane(左:文件列表+提交面板 / 右:Diff)
import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs

import FluentQML as Fluent
import "../components"

Item {
    id: root

    // 当前选中的文件(用于 diff)
    property string selectedPath: ""
    property bool selectedStaged: false

    // ==================== 数据加载 ====================
    function reload() {
        branchLabel.text = (GitBridge && GitBridge.repoPath) ? GitBridge.getCurrentBranch() : ""
        changeModel.clear()
        if (!GitBridge || !GitBridge.repoPath) return
        var list = GitBridge.getStatus()
        for (var i = 0; i < list.length; i++) changeModel.append(list[i])
    }

    function showDiff(path, staged) {
        root.selectedPath = path
        root.selectedStaged = staged
        diffView.text = (GitBridge && path) ? GitBridge.getDiff(path, staged) : ""
    }

    Connections {
        target: GitBridge
        function onStatusChanged() { root.reload() }
        function onOperationFinished(ok, msg) {
            console.log("operation:", ok, msg)
            root.reload()
        }
    }

    Component.onCompleted: root.reload()

    ListModel { id: changeModel }

    // ==================== 布局 ====================
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Fluent.Enums.spacing.xl
        spacing: Fluent.Enums.spacing.l

        // ---------- Header ----------
        RowLayout {
            Layout.fillWidth: true
            spacing: Fluent.Enums.spacing.m

            Text {
                text: "仓库"
                font.pixelSize: Fluent.Enums.typography.displayLarge
                font.bold: true
                color: Fluent.Enums.textColor.primary
                font.family: Fluent.Enums.fontFamily
            }
            Text {
                id: branchLabel
                visible: text !== ""
                color: Fluent.Enums.accentColor
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.body
                font.bold: true
            }
            Item { Layout.fillWidth: true }

            Fluent.Button { text: "打开"; icon: Fluent.Enums.icon.folder; onClicked: folderDialog.open() }
            Fluent.Button { text: "克隆"; icon: Fluent.Enums.icon.cloud; onClicked: cloneDialog.open() }
            Fluent.Button { text: "初始化"; icon: Fluent.Enums.icon.add; onClicked: initFolderDialog.open() }
            Fluent.Button { text: "拉取"; icon: Fluent.Enums.icon.arrow_download; onClicked: GitBridge.pull() }
            Fluent.Button { text: "推送"; icon: Fluent.Enums.icon.arrow_upload; onClicked: GitBridge.push() }
        }

        Text {
            id: repoPathLabel
            Layout.fillWidth: true
            text: (GitBridge && GitBridge.repoPath) ? GitBridge.repoPath : "未打开仓库"
            color: Fluent.Enums.textColor.tertiary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.caption
            elide: Text.ElideMiddle
        }

        // ---------- 主体分栏 ----------
        Fluent.SplitPane {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal
            splitPosition: 0.42

            firstContent: Item {
                anchors.fill: parent

                ColumnLayout {
                    anchors.fill: parent
                    anchors.rightMargin: Fluent.Enums.spacing.m
                    spacing: Fluent.Enums.spacing.s

                    // 文件列表工具条
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "变更 (" + changeModel.count + ")"
                            color: Fluent.Enums.textColor.primary
                            font.family: Fluent.Enums.fontFamily
                            font.pixelSize: Fluent.Enums.typography.bodyLarge
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Fluent.Button {
                            text: "全部暂存"
                            style: Fluent.Enums.button.style_transparent
                            onClicked: GitBridge.stageAll()
                        }
                        Fluent.Button {
                            text: "全部取消"
                            style: Fluent.Enums.button.style_transparent
                            onClicked: GitBridge.unstageAll()
                        }
                    }

                    // 变更文件列表(Fluent.ListView 自带 Fluent 滚动条)
                    Fluent.ListView {
                        id: changeListView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        framed: false
                        spacing: 2
                        model: changeModel
                        delegate: Rectangle {
                            width: changeListView.listView ? changeListView.listView.width : 0
                            height: 40
                            radius: Fluent.Enums.radius.small
                            color: hover.hovered ? Fluent.Enums.stateColor.hover : "transparent"

                            HoverHandler { id: hover }
                            TapHandler { onTapped: root.showDiff(model.path, model.staged) }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: Fluent.Enums.spacing.m
                                anchors.rightMargin: Fluent.Enums.spacing.s
                                spacing: Fluent.Enums.spacing.m

                                Text {
                                    text: model.statusText
                                    Layout.preferredWidth: 50
                                    color: model.staged ? Fluent.Enums.statusLevel.successColor : Fluent.Enums.textColor.tertiary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.caption
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: model.path
                                    color: Fluent.Enums.textColor.primary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.body
                                    elide: Text.ElideMiddle
                                }
                                Fluent.Button {
                                    text: model.staged ? "取消" : "暂存"
                                    style: Fluent.Enums.button.style_transparent
                                    visible: hover.hovered
                                    onClicked: {
                                        if (model.staged) GitBridge.unstageFile(model.path)
                                        else GitBridge.stageFile(model.path)
                                    }
                                }
                                Fluent.Button {
                                    text: "丢弃"
                                    style: Fluent.Enums.button.style_transparent
                                    visible: hover.hovered && !model.staged
                                    onClicked: GitBridge.discardFile(model.path)
                                }
                                Fluent.Button {
                                    text: "历史"
                                    style: Fluent.Enums.button.style_transparent
                                    visible: hover.hovered
                                    onClicked: fileHistoryDialog.openFor(model.path)
                                }
                            }
                        }
                    }

                    // 提交面板
                    Fluent.LineEdit {
                        id: commitInput
                        Layout.fillWidth: true
                        placeholderText: "提交信息"
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Fluent.Enums.spacing.m
                        Fluent.Button {
                            text: "提交"
                            style: Fluent.Enums.button.style_primary
                            enabled: commitInput.text.length > 0
                            onClicked: {
                                var res = GitBridge.commit(commitInput.text)
                                if (res[0]) commitInput.text = ""
                                console.log("commit:", res[0], res[1])
                            }
                        }
                        Fluent.Button {
                            text: "一键提交推送"
                            enabled: commitInput.text.length > 0
                            onClicked: {
                                GitBridge.quickCommitPush(commitInput.text)
                                commitInput.text = ""
                            }
                        }
                    }
                }
            }

            secondContent: Item {
                anchors.fill: parent

                Rectangle {
                    anchors.fill: parent
                    anchors.leftMargin: Fluent.Enums.spacing.m
                    radius: Fluent.Enums.radius.large
                    color: Fluent.Enums.cardColor
                    border.width: Fluent.Enums.border.normal
                    border.color: Fluent.Enums.stateColor.border

                    Flickable {
                        id: diffFlick
                        anchors.fill: parent
                        anchors.margins: Fluent.Enums.spacing.m
                        clip: true
                        contentWidth: diffView.paintedWidth
                        contentHeight: diffView.paintedHeight

                        TextEdit {
                            id: diffView
                            width: diffFlick.width
                            readOnly: true
                            selectByMouse: true
                            wrapMode: TextEdit.NoWrap
                            font.family: "Consolas, Cascadia Code, monospace"
                            font.pixelSize: Fluent.Enums.typography.body
                            color: Fluent.Enums.textColor.primary
                            text: root.selectedPath === "" ? "选择文件查看差异" : ""
                        }
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
            if (GitBridge.setRepoPath(path)) root.reload()
            else console.warn("不是有效的 Git 仓库: " + path)
        }
    }

    // 克隆对话框
    CloneDialog {
        id: cloneDialog
        onCloneRequested: function(url, path) { GitBridge.clone(url, path) }
    }

    // 初始化:先选目录,再走引导
    FolderDialog {
        id: initFolderDialog
        title: "选择要初始化的目录"
        onAccepted: {
            var path = selectedFolder.toString().replace(/^file:\/\/\//, "")
            var res = GitBridge.initRepo(path)
            if (res[0]) {
                GitBridge.setRepoPath(path)
                initGuide.repoPath = path
                initGuide.currentIndex = 0
                initGuide.show()
            } else {
                console.warn("初始化失败:", res[1])
            }
        }
    }

    // 初始化引导(窗口)
    InitRepoGuide {
        id: initGuide
        onCompleted: function(p) { root.reload() }
    }

    // 文件历史
    FileHistoryDialog { id: fileHistoryDialog }
}
