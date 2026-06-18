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

    property var allCommits: []        // 已加载的提交(累积)
    property var timelineItems: []      // 按日期分组的 Timeline items

    // ==================== 数据加载 ====================
    function resetAndLoad() {
        root.allCommits = []
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
        root.allCommits = root.allCommits.concat(batch)
        root.loadedCount += batch.length
        root.hasMore = batch.length === root.pageSize
        root.loading = false
        rebuildTimeline()
    }

    function doSearch(query) {
        if (query === "") { resetAndLoad(); return }
        if (!GitBridge || !GitBridge.repoPath) return
        root.searchMode = true
        root.allCommits = GitBridge.searchCommits(query, "all", 100)
        rebuildTimeline()
    }

    // 提交日期 -> 分组标签(今天/昨天/本周/更早 + 日期)
    function _dateGroup(dateStr) {
        var d = (dateStr || "").substring(0, 10)  // "YYYY-MM-DD"
        if (d === "") return "未知日期"
        var today = new Date()
        var pad = function(n) { return n < 10 ? "0" + n : "" + n }
        var todayStr = today.getFullYear() + "-" + pad(today.getMonth() + 1) + "-" + pad(today.getDate())
        var y = new Date(today.getTime() - 86400000)
        var yStr = y.getFullYear() + "-" + pad(y.getMonth() + 1) + "-" + pad(y.getDate())
        if (d === todayStr) return "今天"
        if (d === yStr) return "昨天"
        return d
    }

    // 把 allCommits 按日期分组成 Timeline.items
    function rebuildTimeline() {
        var groups = []
        var indexByLabel = ({})
        for (var i = 0; i < root.allCommits.length; i++) {
            var c = root.allCommits[i]
            var label = _dateGroup(c.date)
            if (indexByLabel[label] === undefined) {
                indexByLabel[label] = groups.length
                groups.push({ "title": label, "status": "info", "cards": [] })
            }
            groups[indexByLabel[label]].cards.push({
                "text": c.message,
                "description": c.shortHash + " · " + c.author,
                "commit": c
            })
        }
        root.timelineItems = groups
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
                    subtitle: root.searchMode ? (root.allCommits.length + " 条搜索结果") : (root.allCommits.length + " 条提交")
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

                // 提交时间线(按日期分组,用 Fluent.Timeline 封装)
                Fluent.ScrollArea {
                    id: timelineScroll
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    // 滚动触底自动加载下一批
                    onContentYChanged: {
                        if (contentHeight > height
                            && contentY + height >= contentHeight - 120
                            && !root.loading && root.hasMore && !root.searchMode)
                            root.loadMore()
                    }

                    // 首屏内容未填满视口时继续加载,保证可滚动
                    onContentHeightChanged: {
                        if (contentHeight > 0 && contentHeight <= height
                            && !root.loading && root.hasMore && !root.searchMode)
                            root.loadMore()
                    }

                    Column {
                        width: timelineScroll.width - Fluent.Enums.spacing.l
                        spacing: Fluent.Enums.spacing.m

                        Fluent.Timeline {
                            width: parent.width
                            items: root.timelineItems
                            onCardClickedData: function(groupIndex, cardIndex, cardData) {
                                if (cardData && cardData.commit)
                                    root.selectedCommit = cardData.commit
                            }
                        }

                        // 加载状态提示
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            visible: root.loading
                            text: "加载中..."
                            color: Fluent.Enums.textColor.tertiary
                            font.family: Fluent.Enums.fontFamily
                            font.pixelSize: Fluent.Enums.typography.caption
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
