import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Rectangle {
    id: root

    objectName: "historyCommitFilesPanel"
    radius: Fluent.Enums.radius.medium
    color: Fluent.Enums.surfaceColor
    border.width: Fluent.Enums.border.thin
    border.color: Fluent.Enums.stateColor.borderLight

    property var commit: null
    property bool loading: false
    property string requestRepoPath: ""
    property string requestHash: ""
    property bool componentReady: false

    function reload() {
        commitFilesModel.clear()
        root.loading = false
        root.requestRepoPath = ""
        root.requestHash = ""
        if (!root.commit || !GitBridge || !GitBridge.repoPath) return

        var hash = root.commit.hash || ""
        if (hash === "") return
        root.requestRepoPath = GitBridge.repoPath
        root.requestHash = hash
        root.loading = true
        GitBridge.requestCommitFiles(hash)
    }

    function countStatus(status) {
        var count = 0
        for (var i = 0; i < commitFilesModel.count; i++) {
            if (commitFilesModel.get(i).status === status) count++
        }
        return count
    }

    function displayPath(path) {
        return (path || "").replace(/\t/g, " → ")
    }

    Component.onCompleted: {
        root.componentReady = true
        root.reload()
    }
    onCommitChanged: if (root.componentReady) root.reload()

    Connections {
        target: GitBridge
        function onCommitFilesReady(repoPath, hash, files) {
            if (!GitBridge || repoPath !== GitBridge.repoPath) return
            if (repoPath !== root.requestRepoPath || hash !== root.requestHash) return
            if (!root.commit || root.commit.hash !== hash) return
            commitFilesModel.clear()
            for (var i = 0; i < files.length; i++) commitFilesModel.append(files[i])
            root.loading = false
        }
    }

    ListModel { id: commitFilesModel }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Fluent.Enums.spacing.m
        spacing: Fluent.Enums.spacing.s

        RowLayout {
            Layout.fillWidth: true
            spacing: Fluent.Enums.spacing.s

            Text {
                text: "变更文件"
                color: Fluent.Enums.textColor.primary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.body
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            Text {
                text: root.loading ? "正在读取..." : commitFilesModel.count + " 个文件"
                color: Fluent.Enums.textColor.tertiary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
            }
        }

        Flow {
            Layout.fillWidth: true
            spacing: Fluent.Enums.spacing.xs
            visible: !root.loading && commitFilesModel.count > 0

            Fluent.Tag {
                visible: root.countStatus("A") > 0
                status: Fluent.Enums.statusLevel.success
                text: "新增 " + root.countStatus("A")
            }
            Fluent.Tag {
                visible: root.countStatus("M") > 0
                status: Fluent.Enums.statusLevel.info
                text: "修改 " + root.countStatus("M")
            }
            Fluent.Tag {
                visible: root.countStatus("D") > 0
                status: Fluent.Enums.statusLevel.error
                text: "删除 " + root.countStatus("D")
            }
            Fluent.Tag {
                visible: root.countStatus("R") > 0
                status: Fluent.Enums.statusLevel.warning
                text: "重命名 " + root.countStatus("R")
            }
            Fluent.Tag {
                visible: root.countStatus("C") > 0
                status: Fluent.Enums.statusLevel.info
                text: "复制 " + root.countStatus("C")
            }
        }

        Fluent.ScrollArea {
            id: commitFilesList
            objectName: "historyCommitFilesList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.loading && commitFilesModel.count > 0
            type: Fluent.Enums.scroll.type_list
            itemHeight: Fluent.Enums.controlSize.buttonHeight
            listSpacing: Fluent.Enums.spacing.none
            reuseItems: true
            bounceEnabled: false
            padding: 0
            model: commitFilesModel
            delegate: Item {
                width: ListView.view ? ListView.view.width : 0
                height: commitFilesList.itemHeight

                RowLayout {
                    anchors.fill: parent
                    spacing: Fluent.Enums.spacing.s

                    Fluent.Tag {
                        status: model.status === "A"
                            ? Fluent.Enums.statusLevel.success
                            : (model.status === "D"
                                ? Fluent.Enums.statusLevel.error
                                : (model.status === "R"
                                    ? Fluent.Enums.statusLevel.warning
                                    : Fluent.Enums.statusLevel.info))
                        text: model.statusText
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.displayPath(model.path)
                        color: Fluent.Enums.textColor.secondary
                        font.family: "Consolas, monospace"
                        font.pixelSize: Fluent.Enums.typography.caption
                        elide: Text.ElideMiddle
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.loading || commitFilesModel.count === 0
            text: root.loading ? "正在读取此提交的文件变更..." : "未检测到文件变更"
            color: Fluent.Enums.textColor.tertiary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.bodySmall
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }
}
