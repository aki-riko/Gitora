// 历史视图(阶段 2:迁移 history_interface.py)
// 布局:SplitPane(左:搜索+提交列表(分页无限滚动) / 右:提交详情+操作)
import QtQuick
import QtQuick.Layouts

import FluentQML as Fluent
import "../components"

Item {
    id: root

    readonly property int pageSize: 30
    property int loadedCount: 0
    property bool hasMore: true
    property bool loading: false
    property bool searchMode: false
    property var selectedCommit: null

    ListModel { id: commitModel }

    // ==================== 数据加载 ====================
    function resetAndLoad() {
        commitModel.clear()
        root.loadedCount = 0
        root.hasMore = true
        root.searchMode = false
        loadMore()
    }

    function loadMore() {
        if (root.loading || !root.hasMore || root.searchMode) return
        if (!GitBridge || !GitBridge.repoPath) return
        root.loading = true
        var fast = GitBridge.isLargeRepo()
        var batch = GitBridge.getLog(root.pageSize, root.loadedCount, fast)
        for (var i = 0; i < batch.length; i++) commitModel.append(batch[i])
        root.loadedCount += batch.length
        root.hasMore = batch.length === root.pageSize
        root.loading = false
    }

    function doSearch(query) {
        if (query === "") { resetAndLoad(); return }
        if (!GitBridge || !GitBridge.repoPath) return
        root.searchMode = true
        commitModel.clear()
        var results = GitBridge.searchCommits(query, "all", 100)
        for (var i = 0; i < results.length; i++) commitModel.append(results[i])
    }

    Connections {
        target: GitBridge
        function onStatusChanged() { root.resetAndLoad() }
    }

    function _op(res) {
        console.log("操作结果:", res[0], res[1])
        if (res[0]) root.resetAndLoad()
    }

    Component.onCompleted: root.resetAndLoad()

    // ==================== 布局 ====================
    Fluent.SplitPane {
        anchors.fill: parent
        anchors.margins: Fluent.Enums.spacing.xl
        orientation: Qt.Horizontal
        splitPosition: 0.55

        firstContent: Item {
            anchors.fill: parent

            ColumnLayout {
                anchors.fill: parent
                anchors.rightMargin: Fluent.Enums.spacing.m
                spacing: Fluent.Enums.spacing.m

                // 标题 + 搜索
                PageHeader {
                    title: "历史"
                    subtitle: root.searchMode ? (commitModel.count + " 条搜索结果") : (commitModel.count + " 条提交")
                    Fluent.LineEdit {
                        id: searchInput
                        width: 240
                        placeholderText: "搜索提交(消息/作者)"
                        onTextChanged: searchDebounce.restart()
                    }
                    Fluent.Button {
                        text: "Reflog"
                        icon: Fluent.Enums.icon.history
                        onClicked: reflogDialog.openReflog()
                    }
                }

                Timer {
                    id: searchDebounce
                    interval: 300
                    onTriggered: root.doSearch(searchInput.text)
                }

                // 提交列表(时间线视觉 + Fluent 滚动条)
                // 提交列表(Fluent.ListView 自带 Fluent 滚动条 + 时间线视觉)
                Fluent.ListView {
                    id: commitListView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    framed: false
                    model: commitModel

                    Connections {
                        target: commitListView.listView
                        function onContentYChanged() {
                            var lv = commitListView.listView
                            if (lv.atYEnd && !root.loading && root.hasMore && !root.searchMode)
                                root.loadMore()
                        }
                    }

                    delegate: Item {
                            width: commitListView.listView ? commitListView.listView.width : 0
                            height: 64
                            readonly property bool isSel: root.selectedCommit && root.selectedCommit.hash === model.hash

                            // 时间线:左侧连接线 + 圆点
                            Rectangle {
                                x: 11; y: 0
                                width: Fluent.Enums.border.normal
                                height: parent.height + Fluent.Enums.spacing.s
                                color: Fluent.Enums.stateColor.border
                                visible: index < commitListView.count - 1
                            }
                            Rectangle {
                                x: 6; y: 24
                                width: 12; height: 12; radius: 6
                                color: parent.isSel ? Fluent.Enums.accentColor : Fluent.Enums.cardColor
                                border.width: Fluent.Enums.border.normal
                                border.color: Fluent.Enums.accentColor
                                z: 1
                            }

                            // 提交卡片
                            Rectangle {
                                x: 28
                                width: parent.width - 28
                                height: 60
                                radius: Fluent.Enums.radius.large
                                color: parent.isSel
                                       ? Fluent.Enums.stateColor.hover
                                       : (cardHover.hovered ? Fluent.Enums.stateColor.hover : Fluent.Enums.cardColor)
                                border.width: Fluent.Enums.border.normal
                                border.color: parent.isSel ? Fluent.Enums.accentColor : Fluent.Enums.stateColor.border

                                HoverHandler { id: cardHover }
                                TapHandler {
                                    onTapped: root.selectedCommit = {
                                        "hash": model.hash, "shortHash": model.shortHash,
                                        "author": model.author, "email": model.email,
                                        "date": model.date, "message": model.message, "branch": model.branch
                                    }
                                }

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: Fluent.Enums.spacing.m
                                    spacing: 2
                                    Text {
                                        Layout.fillWidth: true
                                        text: model.message
                                        color: Fluent.Enums.textColor.primary
                                        font.family: Fluent.Enums.fontFamily
                                        font.pixelSize: Fluent.Enums.typography.body
                                        font.bold: true
                                        elide: Text.ElideRight
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: Fluent.Enums.spacing.m
                                        Text {
                                            text: model.shortHash
                                            color: Fluent.Enums.accentColor
                                            font.family: "Consolas, monospace"
                                            font.pixelSize: Fluent.Enums.typography.caption
                                        }
                                        Text {
                                            text: model.author + " · " + model.date
                                            color: Fluent.Enums.textColor.tertiary
                                            font.family: Fluent.Enums.fontFamily
                                            font.pixelSize: Fluent.Enums.typography.caption
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                    }
                                }
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

                // 空状态
                Fluent.EmptyState {
                    anchors.centerIn: parent
                    visible: !root.selectedCommit
                    icon: Fluent.Enums.icon.history
                    title: "未选择提交"
                    description: "从左侧时间线选择一个提交查看详情"
                }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Fluent.Enums.spacing.l
                    spacing: Fluent.Enums.spacing.m
                    visible: !!root.selectedCommit

                    Text {
                        Layout.fillWidth: true
                        text: root.selectedCommit ? root.selectedCommit.message : ""
                        color: Fluent.Enums.textColor.primary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.titleLarge
                        font.bold: true
                        wrapMode: Text.WordWrap
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: Fluent.Enums.spacing.l
                        rowSpacing: Fluent.Enums.spacing.s
                        Text { text: "Hash"; color: Fluent.Enums.textColor.tertiary; font.family: Fluent.Enums.fontFamily; font.pixelSize: Fluent.Enums.typography.caption }
                        Text { text: root.selectedCommit ? root.selectedCommit.hash : ""; color: Fluent.Enums.textColor.secondary; font.family: "Consolas, monospace"; font.pixelSize: Fluent.Enums.typography.caption; Layout.fillWidth: true; elide: Text.ElideRight }
                        Text { text: "作者"; color: Fluent.Enums.textColor.tertiary; font.family: Fluent.Enums.fontFamily; font.pixelSize: Fluent.Enums.typography.caption }
                        Text { text: root.selectedCommit ? (root.selectedCommit.author + " <" + root.selectedCommit.email + ">") : ""; color: Fluent.Enums.textColor.secondary; font.family: Fluent.Enums.fontFamily; font.pixelSize: Fluent.Enums.typography.caption; Layout.fillWidth: true; elide: Text.ElideRight }
                        Text { text: "时间"; color: Fluent.Enums.textColor.tertiary; font.family: Fluent.Enums.fontFamily; font.pixelSize: Fluent.Enums.typography.caption }
                        Text { text: root.selectedCommit ? root.selectedCommit.date : ""; color: Fluent.Enums.textColor.secondary; font.family: Fluent.Enums.fontFamily; font.pixelSize: Fluent.Enums.typography.caption }
                    }

                    Item { Layout.fillHeight: true }

                    // 操作按钮
                    Flow {
                        Layout.fillWidth: true
                        spacing: Fluent.Enums.spacing.m
                        Fluent.Button {
                            text: "复制 Hash"
                            style: Fluent.Enums.button.style_transparent
                            onClicked: if (root.selectedCommit && ClipboardHelper) ClipboardHelper.copy(root.selectedCommit.hash)
                        }
                        Fluent.Button {
                            text: "详情"
                            style: Fluent.Enums.button.style_transparent
                            onClicked: if (root.selectedCommit) commitDetailDialog.openFor(root.selectedCommit.hash)
                        }
                        Fluent.Button {
                            text: "Checkout"
                            onClicked: root._op(GitBridge.checkoutCommit(root.selectedCommit.hash))
                        }
                        Fluent.Button {
                            text: "Cherry-pick"
                            onClicked: root._op(GitBridge.cherryPick(root.selectedCommit.hash))
                        }
                        Fluent.Button {
                            text: "Revert"
                            onClicked: root._op(GitBridge.revertCommit(root.selectedCommit.hash))
                        }
                        Fluent.Button {
                            text: "Reset (mixed)"
                            style: Fluent.Enums.button.style_primary
                            onClicked: {
                                resetDanger.content = "将回滚到提交 " + root.selectedCommit.shortHash
                                    + "\n(mixed 模式:保留工作区改动,重置暂存区)\n此操作会改变提交历史。"
                                resetDanger._hash = root.selectedCommit.hash
                                resetDanger.start()
                            }
                        }
                    }
                }
            }
        }
    }

    // 危险操作:reset 二次确认
    DangerDialog {
        id: resetDanger
        title: "确认 Reset"
        countdown: 3
        property string _hash: ""
        onConfirmed: root._op(GitBridge.resetToCommit(_hash, "mixed"))
    }

    // 提交详情
    CommitDetailDialog { id: commitDetailDialog }

    // 引用日志
    ReflogDialog {
        id: reflogDialog
        onCheckoutRequested: function(h) { root._op(GitBridge.checkoutCommit(h)) }
    }
}
