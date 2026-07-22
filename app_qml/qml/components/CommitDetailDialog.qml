// 提交详情对话框(基于 DialogBoxCore 自定义,标题自绘避免与 MessageBox 自带 title 重叠)
// 只读展示:提交信息 + 变更文件列表 + 完整 diff
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.DialogBoxCore {
    id: dlg

    readonly property real viewportRatio: 0.92
    readonly property int _targetDialogWidth: Math.max(
        Fluent.Enums.dialog.minWidth - Fluent.Enums.dialog.contentPadding,
        Math.floor(dlg.width * dlg.viewportRatio) - Fluent.Enums.dialog.contentPadding)
    readonly property int _targetContentHeight: Math.max(
        1,
        Math.floor(dlg.height * dlg.viewportRatio)
            - Fluent.Enums.dialog.actionsRowHeight
            - Fluent.Enums.dialog.contentPadding)
    contentWidth: dlg._targetDialogWidth

    property string commitHash: ""
    property string _requestRepoPath: ""
    property string _author: ""
    property string _shortHash: ""
    property string _date: ""
    property string _rawDiff: ""
    property string _selectedFilePath: ""
    ListModel { id: filesModel }

    function clearContent() {
        dlg.commitHash = ""
        dlg._requestRepoPath = ""
        dlg._author = ""
        dlg._shortHash = ""
        dlg._date = ""
        dlg._rawDiff = ""
        dlg._selectedFilePath = ""
        msgLabel.text = ""
        filesModel.clear()
        commitDiffViewer.clearDiff()
    }

    function openFor(hash) {
        dlg.commitHash = hash
        dlg._requestRepoPath = (GitBridge && GitBridge.repoPath) ? GitBridge.repoPath : ""
        var d = GitBridge.getCommitDetail(hash) || ({})
        msgLabel.text = d.message || ""
        dlg._author = d.author || ""
        dlg._shortHash = d.shortHash || ""
        dlg._date = d.date || ""
        dlg._rawDiff = ""
        dlg._selectedFilePath = ""
        filesModel.clear()
        commitDiffViewer.setLoading("加载中...")
        GitBridge.requestCommitFiles(hash)
        GitBridge.requestCommitDiff(hash)
        dlg.open()
    }

    Connections {
        target: GitBridge
        function onRepoPathChanged(path) { dlg.clearContent() }
        function onCommitFilesReady(repoPath, hash, files) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== dlg._requestRepoPath || hash !== dlg.commitHash) return
            filesModel.clear()
            for (var i = 0; i < files.length; i++) filesModel.append(files[i])
        }
        function onCommitDiffReady(repoPath, hash, diff) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== dlg._requestRepoPath || hash !== dlg.commitHash) return
            dlg._rawDiff = diff || ""
            commitDiffViewer.rawDiff = dlg._rawDiff
            commitDiffViewer.filterPath = dlg._selectedFilePath
        }
    }

    // 底部关闭按钮
    footer: Component {
        Row {
            Fluent.ButtonCore {
                text: "关闭"
                style: Fluent.Enums.button.style_primary
                width: Fluent.Enums.dialog.buttonWidth
                height: Fluent.Enums.dialog.buttonHeight
                onClicked: dlg.reject()
            }
        }
    }

    // ==================== 内容 ====================
    ColumnLayout {
        width: dlg.contentWidth
        height: dlg._targetContentHeight
        spacing: Fluent.Enums.spacing.l

        // ── 头部:头像 + 消息标题 + 元信息 ──
        RowLayout {
            id: headerLayout
            Layout.fillWidth: true
            Layout.fillHeight: false
            Layout.preferredHeight: implicitHeight
            Layout.maximumHeight: implicitHeight
            spacing: Fluent.Enums.spacing.m

            Fluent.Avatar {
                size: 40
                text: dlg._author
                Layout.alignment: Qt.AlignTop
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Fluent.Enums.spacing.xs

                // 提交消息标题(限高,过长可滚动;ScrollArea 自带平滑滚动条)
                Fluent.ScrollArea {
                    Layout.fillWidth: true
                    Layout.fillHeight: false
                    Layout.preferredHeight: Math.min(msgLabel.implicitHeight, 96)
                    Layout.maximumHeight: Math.min(msgLabel.implicitHeight, 96)
                    padding: 0
                    Text {
                        id: msgLabel
                        width: parent ? parent.width : 0
                        color: Fluent.Enums.textColor.primary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.subtitle
                        font.bold: true
                        wrapMode: Text.WordWrap
                    }
                }

                // 元信息行:作者 · 时间
                Text {
                    Layout.fillWidth: true
                    text: dlg._author + "  ·  " + dlg._date
                    color: Fluent.Enums.textColor.tertiary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.caption
                    elide: Text.ElideRight
                }
                // hash(等宽)
                Text {
                    Layout.fillWidth: true
                    text: dlg.commitHash
                    color: Fluent.Enums.textColor.tertiary
                    font.family: "Consolas, monospace"
                    font.pixelSize: Fluent.Enums.typography.caption
                    elide: Text.ElideRight
                }
            }
        }

        Fluent.Separator { Layout.fillWidth: true }

        // ── 变更文件 ──(ScrollArea 自带平滑滚动条;文件数少,默认模式 Repeater 即可)
        Fluent.Label {
            text: "变更文件 (" + filesModel.count + ")"
            type: Fluent.Enums.label.type_body_strong
            color: Fluent.Enums.textColor.secondary
        }
        Fluent.ScrollArea {
            id: filesScrollArea
            Layout.fillWidth: true
            Layout.fillHeight: false
            Layout.preferredHeight: Math.min(filesModel.count * 24 + 4, 110)
            Layout.maximumHeight: Math.min(filesModel.count * 24 + 4, 110)
            padding: 0
            Column {
                // 绑 ScrollArea 自身宽度而非 parent:content 被塞进内部 Loader,
                // parent(contentHolder)在 Loader 实例化时序里会短暂为 null,
                // 读 parent.width 会报 "Cannot read property 'width' of null"。
                width: filesScrollArea.width
                Repeater {
                    model: filesModel
                    delegate: Rectangle {
                        width: parent.width
                        height: 24
                        radius: Fluent.Enums.radius.micro
                        readonly property bool isSelected: dlg._selectedFilePath === model.path
                        color: isSelected ? Fluent.Enums.stateColor.hover : (fileHover.hovered ? Fluent.Enums.stateColor.hover : "transparent")

                        HoverHandler { id: fileHover }
                        TapHandler {
                            onTapped: {
                                dlg._selectedFilePath = model.path
                                commitDiffViewer.filterPath = model.path
                            }
                        }

                        Row {
                            anchors.fill: parent
                            spacing: Fluent.Enums.spacing.m
                            Text {
                                text: model.statusText
                                width: 50
                                color: Fluent.Enums.textColor.tertiary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.caption
                                verticalAlignment: Text.AlignVCenter
                                height: parent.height
                            }
                            Text {
                                width: parent.width - 50 - Fluent.Enums.spacing.m
                                text: model.path
                                color: Fluent.Enums.textColor.primary
                                font.family: "Consolas, monospace"
                                font.pixelSize: Fluent.Enums.typography.caption
                                elide: Text.ElideMiddle
                                verticalAlignment: Text.AlignVCenter
                                height: parent.height
                            }
                        }
                    }
                }
            }
        }

        Fluent.Separator { Layout.fillWidth: true }

        // ── diff ──(ScrollArea 自带平滑滚动条,外层 Rectangle 提供边框)
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Fluent.Enums.radius.medium
            color: Fluent.Enums.cardColor
            border.width: Fluent.Enums.border.normal
            border.color: Fluent.Enums.stateColor.border
            DiffViewer {
                id: commitDiffViewer
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.s
                onFilterChanged: function(path) {
                    dlg._selectedFilePath = path
                }
            }
        }
    }
}
