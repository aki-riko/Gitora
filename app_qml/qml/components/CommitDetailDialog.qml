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
    property var fileRows: []
    property int totalFileCount: 0
    property bool filesTruncated: false

    function clearContent() {
        dlg.commitHash = ""
        dlg._requestRepoPath = ""
        dlg._author = ""
        dlg._shortHash = ""
        dlg._date = ""
        dlg._rawDiff = ""
        dlg._selectedFilePath = ""
        dlg.fileRows = []
        dlg.totalFileCount = 0
        dlg.filesTruncated = false
        msgLabel.text = ""
        commitDiffViewer.clearDiff()
    }

    function openFor(hash) {
        dlg.commitHash = hash
        dlg._requestRepoPath = (GitBridge && GitBridge.repoPath) ? GitBridge.repoPath : ""
        msgLabel.text = "加载中..."
        dlg._author = ""
        dlg._shortHash = ""
        dlg._date = ""
        var detailTask = GitBridge.getCommitDetail(hash)
        var requestRepo = dlg._requestRepoPath
        detailTask.succeeded.connect(function(detail) {
            if (!GitBridge || GitBridge.repoPath !== requestRepo
                    || dlg.commitHash !== hash) return
            var d = detail || ({})
            msgLabel.text = d.message || ""
            dlg._author = d.author || ""
            dlg._shortHash = d.shortHash || ""
            dlg._date = d.date || ""
        })
        dlg._rawDiff = ""
        dlg._selectedFilePath = ""
        dlg.fileRows = []
        dlg.totalFileCount = 0
        dlg.filesTruncated = false
        commitDiffViewer.setLoading("加载中...")
        GitBridge.requestCommitFiles(hash)
        GitBridge.requestCommitDiff(hash)
        dlg.open()
    }

    Connections {
        target: GitBridge
        function onRepoPathChanged(path) { dlg.clearContent() }
        function onCommitFilesReady(repoPath, hash, files, total, isTruncated, counts) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== dlg._requestRepoPath || hash !== dlg.commitHash) return
            dlg.fileRows = files || []
            dlg.totalFileCount = total || dlg.fileRows.length
            dlg.filesTruncated = !!isTruncated
        }
        function onCommitDiffReady(repoPath, hash, diff) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== dlg._requestRepoPath || hash !== dlg.commitHash) return
            dlg._rawDiff = diff || ""
            commitDiffViewer.setDiff(dlg._rawDiff, dlg._selectedFilePath)
        }
        function onCommitFileDiffReady(repoPath, hash, path, diff) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== dlg._requestRepoPath
                    || hash !== dlg.commitHash || path !== dlg._selectedFilePath) return
            dlg._rawDiff = diff || ""
            commitDiffViewer.setDiff(dlg._rawDiff, "")
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

                // 元信息单行:作者 · 时间 · 短 hash
                Text {
                    Layout.fillWidth: true
                    text: dlg._author + "  ·  " + dlg._date + "  ·  " + dlg._shortHash
                    color: Fluent.Enums.textColor.tertiary
                    font.family: "Consolas, monospace"
                    font.pixelSize: Fluent.Enums.typography.caption
                    elide: Text.ElideRight
                }
            }
        }

        Fluent.Separator { Layout.fillWidth: true }

        // ── 主体:左栏变更文件 + 右侧 diff 吃满剩余空间 ──
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Fluent.Enums.spacing.l

            // 左栏:变更文件(仅多文件提交显示;文件数少,默认模式 Repeater 即可)
            // 与右侧 diff 共用同一套卡片材质(cardColor + border),标题/状态/行高则与
            // 历史页 CommitFilesPanel 统一,避免同一个"变更文件"在同屏出现两种长相。
            Rectangle {
                visible: dlg.fileRows.length > 1
                Layout.preferredWidth: 240
                Layout.maximumWidth: 240
                Layout.fillHeight: true
                radius: Fluent.Enums.radius.medium
                color: Fluent.Enums.cardColor
                border.width: Fluent.Enums.border.normal
                border.color: Fluent.Enums.stateColor.border

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Fluent.Enums.spacing.m
                    spacing: Fluent.Enums.spacing.s

                    // 标题行:左标题 + 右计数(照 CommitFilesPanel 的标题层次)
                    RowLayout {
                        Layout.fillWidth: true
                        // 与文件行文字起点对齐:行内文字同样让开 6px 强调条间距
                        Layout.leftMargin: Fluent.Enums.spacing.s
                        Layout.rightMargin: Fluent.Enums.spacing.s
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
                            text: dlg.filesTruncated
                                ? dlg.fileRows.length + " / " + dlg.totalFileCount + " 个文件"
                                : dlg.totalFileCount + " 个文件"
                            color: Fluent.Enums.textColor.tertiary
                            font.family: Fluent.Enums.fontFamily
                            font.pixelSize: Fluent.Enums.typography.caption
                        }
                    }

                    Fluent.ScrollArea {
                        id: filesScrollArea
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        padding: 0
                        type: Fluent.Enums.scroll.type_list
                        // 行高改与历史页变更文件列表一致(引擎按钮高 32):
                        // 原来的 24 会把多行挤成一片,且与右侧 diff 的行密度对不上。
                        itemHeight: Fluent.Enums.controlSize.buttonHeight
                        listSpacing: 0
                        reuseItems: true
                        bounceEnabled: false
                        // 关闭 ScrollArea 默认当前项高亮(蓝竖条+浅蓝底):选中态由 delegate 自绘,
                        // 否则引擎 highlight 会与自绘选中底色重叠,且 model 重置后 currentIndex
                        // 落到 0 导致高亮钉死在第一行(照 CommitFilesPanel 同款做法)。
                        selectable: false
                        model: dlg.fileRows
                        delegate: Rectangle {
                            objectName: "commitDetailFileRow"
                            width: ListView.view ? ListView.view.width : 0
                            height: filesScrollArea.itemHeight
                            radius: Fluent.Enums.radius.micro
                            readonly property bool isSelected: dlg._selectedFilePath === modelData.path
                            // 选中用语义选中底色、悬停用列表 hover 层:两者不再共用同一个颜色,
                            // 也不再画闭合蓝框(浅底 + 四边闭合蓝框看起来像聚焦输入框)。
                            color: isSelected
                                ? Fluent.Enums.stateColor.selected
                                : (fileHover.hovered
                                    ? Fluent.Enums.stateColor.listItemHover
                                    : "transparent")

                            // 选中指示条:贴行左缘的短强调条
                            Rectangle {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                width: 2
                                height: parent.height - Fluent.Enums.spacing.m
                                radius: width / 2
                                color: Fluent.Enums.accentColor
                                visible: parent.isSelected
                            }

                            HoverHandler { id: fileHover }
                            TapHandler {
                                onTapped: {
                                    dlg._selectedFilePath = modelData.path
                                    commitDiffViewer.setLoading("加载中...")
                                    GitBridge.requestCommitFileDiff(
                                        dlg.commitHash, dlg._selectedFilePath)
                                }
                            }
                            // 路径被省略时悬浮在行左侧显示完整路径(原生窗口 tooltip,跨弹窗边界)
                            Fluent.ToolTip {
                                x: -width - Fluent.Enums.spacing.s
                                y: (parent.height - height) / 2
                                visible: fileHover.hovered && pathText.truncated
                                text: modelData.path
                            }

                            RowLayout {
                                anchors.fill: parent
                                // 让开左侧强调条,并与标题行文字起点对齐
                                anchors.leftMargin: Fluent.Enums.spacing.s
                                anchors.rightMargin: Fluent.Enums.spacing.s
                                spacing: Fluent.Enums.spacing.m

                                // 状态改彩色 Tag,与历史页变更文件列表同一套状态语言;
                                // 原来的固定 50px 灰字既白占 1/4 宽度,又把路径挤到只剩 130px。
                                Fluent.Tag {
                                    status: modelData.status === "A"
                                        ? Fluent.Enums.statusLevel.success
                                        : (modelData.status === "D"
                                            ? Fluent.Enums.statusLevel.error
                                            : (modelData.status === "R"
                                                ? Fluent.Enums.statusLevel.warning
                                                : Fluent.Enums.statusLevel.info))
                                    text: modelData.statusText
                                }
                                Text {
                                    id: pathText
                                    Layout.fillWidth: true
                                    text: modelData.path
                                    color: Fluent.Enums.textColor.primary
                                    font.family: "Consolas, monospace"
                                    font.pixelSize: Fluent.Enums.typography.caption
                                    elide: Text.ElideMiddle
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }
                        }
                    }
                }
            }

            // 右侧:diff(唯一占满剩余宽高的主体)
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
                }
            }
        }
    }
}
