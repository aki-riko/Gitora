// Tag 视图(阶段 3:迁移 tag_interface.py)
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent
import "../components"

Item {
    id: root
    property string _tagsRequestRepoPath: ""
    property bool _tagsRequesting: false
    property bool _reloadPending: false
    property string _pendingLocalDelete: ""
    property string _pendingRemoteDelete: ""
    property string _pendingRemoteName: ""
    ListModel { id: tagModel }

    function clearModel() {
        root._tagsRequestRepoPath = ""
        root._tagsRequesting = false
        tagModel.clear()
    }

    function reload() {
        if (!GitBridge || !GitBridge.repoPath) {
            clearModel()
            root._reloadPending = false
            return
        }
        // 已加载但不在前台的标签页不抢占切仓库主流程；重新显示时再刷新。
        if (!root.visible) {
            root._reloadPending = true
            return
        }
        if (root._tagsRequesting) {
            root._reloadPending = true
            return
        }
        root._tagsRequesting = true
        root._reloadPending = false
        root._tagsRequestRepoPath = GitBridge.repoPath
        GitBridge.requestTags()  // 异步,结果经 tagsReady 回传
    }

    function _op(res) {
        if (res[0]) {
            Fluent.NotificationManager.desktop.success("成功", res[1] || "操作完成")
            root.reload()
        } else {
            Fluent.NotificationManager.desktop.error("失败", res[1] || "操作失败")
        }
    }

    function _defaultRemoteName() {
        var remotes = GitBridge ? GitBridge.getRemoteInfo() : []
        if (!remotes || remotes.length === 0) return ""
        for (var i = 0; i < remotes.length; i++) {
            if (remotes[i].name === "origin") return "origin"
        }
        return remotes[0].name || ""
    }

    function _askDeleteRemoteTag(name) {
        var remote = root._defaultRemoteName()
        if (!remote) {
            Fluent.NotificationManager.desktop.error("失败", "当前仓库没有远程仓库")
            return
        }
        root._pendingRemoteDelete = name
        root._pendingRemoteName = remote
        deleteRemoteTagDanger.start()
    }

    Connections {
        target: GitBridge
        function onStatusChanged() {
            root._reloadPending = true
            if (root.visible) root.reload()
        }
        function onRepoPathChanged(path) {
            root.clearModel()
            root._reloadPending = true
            if (root.visible) Qt.callLater(function() { root.reload() })
        }
        function onTagsReady(repoPath, list) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== root._tagsRequestRepoPath) return
            tagModel.clear()
            for (var i = 0; i < list.length; i++) tagModel.append(list[i])
            root._tagsRequesting = false
            root._tagsRequestRepoPath = ""
            if (root._reloadPending && root.visible)
                Qt.callLater(function() { root.reload() })
        }
    }
    onVisibleChanged: {
        if (visible && root._reloadPending)
            Qt.callLater(function() { root.reload() })
    }
    Component.onCompleted: {
        root._reloadPending = true
        if (root.visible) Qt.callLater(function() { root.reload() })
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Fluent.Enums.spacing.xl
        spacing: Fluent.Enums.spacing.l

        RowLayout {
            Layout.fillWidth: true
            Layout.maximumWidth: 980
            Layout.alignment: Qt.AlignHCenter
            Text {
                text: "标签 (Tag)"
                font.pixelSize: Fluent.Enums.typography.displayLarge
                font.bold: true
                color: Fluent.Enums.textColor.primary
                font.family: Fluent.Enums.fontFamily
            }
            Item { Layout.fillWidth: true }
            Fluent.Button { text: "刷新"; icon: Fluent.Enums.icon.arrow_sync; onClicked: root.reload() }
            Fluent.Button {
                text: "推送所有"
                enabled: tagModel.count > 0
                onClicked: GitBridge.pushAllTags()  // 异步,反馈经全局 operationFinished
            }
            Fluent.Button {
                text: "创建标签"
                style: Fluent.Enums.button.style_primary
                icon: Fluent.Enums.icon.add
                onClicked: createTagDialog.open()
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.maximumWidth: 980
            Layout.alignment: Qt.AlignHCenter

            Fluent.ScrollArea {
                id: tagList
                anchors.fill: parent
                type: Fluent.Enums.scroll.type_list
                itemHeight: Fluent.Enums.controlSize.buttonHeight + Fluent.Enums.spacing.l * 2
                listSpacing: Fluent.Enums.spacing.m
                listCacheBuffer: 400
                reuseItems: true
                bounceEnabled: false
                padding: 0
                model: tagModel
                delegate: Fluent.Card {
                    width: ListView.view ? ListView.view.width : 0
                    height: tagList.itemHeight
                    RowLayout {
                        id: tagRow
                        anchors.fill: parent
                        spacing: Fluent.Enums.spacing.m
                        Fluent.Icon {
                            icon: Fluent.Enums.icon.tag
                            iconSize: Fluent.Enums.iconSize.l
                            color: Fluent.Enums.accentColor
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            RowLayout {
                                spacing: Fluent.Enums.spacing.m
                                Text {
                                    text: model.name
                                    color: Fluent.Enums.textColor.primary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.body
                                    font.bold: true
                                }
                                Text {
                                    text: model.hash
                                    color: Fluent.Enums.textColor.tertiary
                                    font.family: "Consolas, monospace"
                                    font.pixelSize: Fluent.Enums.typography.caption
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: model.message !== ""
                                text: model.message
                                color: Fluent.Enums.textColor.secondary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.caption
                                elide: Text.ElideRight
                            }
                        }
                        Fluent.Button { text: "检出"; style: Fluent.Enums.button.style_transparent; onClicked: root._op(GitBridge.checkoutTag(model.name)) }
                        Fluent.Button { text: "推送"; style: Fluent.Enums.button.style_transparent; onClicked: GitBridge.pushTag(model.name) }
                        Fluent.Button {
                            text: "删远程"
                            style: Fluent.Enums.button.style_transparent
                            onClicked: root._askDeleteRemoteTag(model.name)
                        }
                        Fluent.Button {
                            text: "删除"
                            style: Fluent.Enums.button.style_transparent
                            onClicked: {
                                root._pendingLocalDelete = model.name
                                deleteLocalTagDanger.start()
                            }
                        }
                    }
                }
            }

            Text {
                anchors.centerIn: parent
                visible: tagModel.count === 0
                text: root._tagsRequesting ? "正在加载 Tag..." : "暂无 Tag"
                color: Fluent.Enums.textColor.tertiary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.body
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    // 创建标签对话框
    Fluent.MessageBox {
        id: createTagDialog
        title: "创建标签"
        confirmText: "创建"
        cancelText: "取消"
        function validate() {
            return tagNameInput.text.trim().length > 0
                && (!tagAnnotatedCheck.checked || tagMsgInput.text.trim().length > 0)
        }
        ColumnLayout {
            width: 320
            spacing: Fluent.Enums.spacing.m
            Fluent.LineEdit { id: tagNameInput; Layout.fillWidth: true; placeholderText: "标签名称(如 v1.0.0)" }
            Fluent.CheckBox {
                id: tagAnnotatedCheck
                text: "附注 Tag"
                checked: false
            }
            Fluent.LineEdit {
                id: tagMsgInput
                Layout.fillWidth: true
                enabled: tagAnnotatedCheck.checked
                placeholderText: tagAnnotatedCheck.checked ? "附注消息" : "轻量 Tag 不需要消息"
            }
        }
        onAccepted: {
            if (tagNameInput.text)
                root._op(GitBridge.createTag(tagNameInput.text, tagMsgInput.text, tagAnnotatedCheck.checked))
            tagNameInput.text = ""
            tagMsgInput.text = ""
            tagAnnotatedCheck.checked = false
        }
    }

    DangerDialog {
        id: deleteLocalTagDanger
        title: "确认删除本地 Tag"
        countdown: 3
        content: "将删除本地标签 \"" + root._pendingLocalDelete + "\"。\n这不会删除远程仓库上的同名 tag。"
        onConfirmed: {
            if (root._pendingLocalDelete)
                root._op(GitBridge.deleteTag(root._pendingLocalDelete))
            root._pendingLocalDelete = ""
        }
    }

    DangerDialog {
        id: deleteRemoteTagDanger
        title: "确认删除远程 Tag"
        countdown: 3
        content: "将从远程 \"" + root._pendingRemoteName + "\" 删除 tag \"" + root._pendingRemoteDelete + "\"。\n"
            + "这会修改远程仓库,但不会删除本地同名 tag。"
        onConfirmed: {
            if (root._pendingRemoteDelete && root._pendingRemoteName)
                GitBridge.deleteRemoteTag(root._pendingRemoteDelete, root._pendingRemoteName)
            root._pendingRemoteDelete = ""
            root._pendingRemoteName = ""
        }
    }
}
