// Tag 视图(阶段 3:迁移 tag_interface.py)
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Item {
    id: root
    property string _tagsRequestRepoPath: ""
    ListModel { id: tagModel }

    function clearModel() {
        root._tagsRequestRepoPath = ""
        tagModel.clear()
    }

    function reload() {
        if (!GitBridge || !GitBridge.repoPath) { clearModel(); return }
        root._tagsRequestRepoPath = GitBridge.repoPath
        GitBridge.requestTags()  // 异步,结果经 tagsReady 回传
    }

    function _op(res) {
        if (res[0]) {
            Fluent.NotificationManager.toast.success(root, "成功", res[1] || "操作完成")
            root.reload()
        } else {
            Fluent.NotificationManager.toast.error(root, "失败", res[1] || "操作失败")
        }
    }

    Connections {
        target: GitBridge
        function onStatusChanged() { root.reload() }
        function onRepoPathChanged(path) {
            root.clearModel()
            root.reload()
        }
        function onTagsReady(repoPath, list) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== root._tagsRequestRepoPath) return
            tagModel.clear()
            for (var i = 0; i < list.length; i++) tagModel.append(list[i])
        }
    }
    Component.onCompleted: root.reload()

    Fluent.ScrollArea {
        anchors.fill: parent
        Column {
            id: tagCol
            width: parent ? parent.width : 0
            spacing: Fluent.Enums.spacing.l
            topPadding: Fluent.Enums.spacing.xl
            bottomPadding: Fluent.Enums.spacing.xl
            // 内容最大宽度受限,超宽屏左右留白(用 padding 让内容靠左但不贴边/不拉满)
            property real sidePad: Math.max(Fluent.Enums.spacing.xxl, (width - 980) / 2)
            leftPadding: sidePad
            rightPadding: sidePad
            readonly property real cw: width - sidePad * 2

            RowLayout {
                width: parent.cw
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

            Text {
                width: parent.cw
                visible: tagModel.count === 0
                text: "暂无 Tag"
                color: Fluent.Enums.textColor.tertiary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.body
                horizontalAlignment: Text.AlignHCenter
                topPadding: Fluent.Enums.spacing.xxl
            }

            Repeater {
                model: tagModel
                delegate: Fluent.Card {
                    width: tagCol.cw
                    height: tagRow.implicitHeight + Fluent.Enums.spacing.l * 2
                    RowLayout {
                        id: tagRow
                        anchors.fill: parent
                        anchors.margins: Fluent.Enums.spacing.l
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
                        Fluent.Button { text: "删除"; style: Fluent.Enums.button.style_transparent; onClicked: root._op(GitBridge.deleteTag(model.name)) }
                    }
                }
            }
        }
    }

    // 创建标签对话框
    Fluent.MessageBox {
        id: createTagDialog
        title: "创建标签"
        confirmText: "创建"
        cancelText: "取消"
        ColumnLayout {
            width: 320
            spacing: Fluent.Enums.spacing.m
            Fluent.LineEdit { id: tagNameInput; Layout.fillWidth: true; placeholderText: "标签名称(如 v1.0.0)" }
            Fluent.LineEdit { id: tagMsgInput; Layout.fillWidth: true; placeholderText: "附注消息(可选)" }
        }
        onAccepted: {
            if (tagNameInput.text)
                root._op(GitBridge.createTag(tagNameInput.text, tagMsgInput.text))
            tagNameInput.text = ""
            tagMsgInput.text = ""
        }
    }
}
