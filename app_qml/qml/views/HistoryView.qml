// 历史视图(阶段 2:迁移 history_interface.py)
// 布局:SplitPane(左:搜索+提交列表(分页无限滚动) / 右:提交详情+操作)
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent
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
        root.timelineItems = []
        root.loadedCount = 0
        root.hasMore = true
        root.searchMode = false
        root.loading = false
        root.selectedCommit = null   // 清空选中,避免详情面板显示过期提交
        loadMore()
    }

    function resetForRepoChange() {
        searchInput.text = ""
        resetAndLoad()
    }

    function loadMore() {
        if (root.loading || !root.hasMore || root.searchMode) return
        if (!GitBridge || !GitBridge.repoPath) return
        root.loading = true
        // 后台分页获取,结果经 logReady 回填
        GitBridge.requestLog(root.pageSize, root.loadedCount)
    }

    function doSearch(query) {
        if (query === "") { resetAndLoad(); return }
        if (!GitBridge || !GitBridge.repoPath) return
        // 进入搜索模式:清空累积状态,防止搜索结果混入普通列表
        root.allCommits = []
        root.loadedCount = 0
        root.hasMore = false        // 搜索结果不分页
        root.loading = false
        root.searchMode = true
        root.selectedCommit = null
        GitBridge.requestSearch(query, "all")
    }

    Connections {
        target: GitBridge
        function onLogReady(repoPath, skip, batch) {
            // 任何过期/不匹配分支都要解锁 loading,否则切仓库后再也无法加载
            if (!GitBridge || repoPath !== GitBridge.repoPath) { root.loading = false; return }
            if (root.searchMode) { root.loading = false; return }
            if (skip !== root.loadedCount) { root.loading = false; return }
            root.allCommits = root.allCommits.concat(batch)
            root.loadedCount += batch.length
            root.hasMore = batch.length === root.pageSize
            root.loading = false
            rebuildTimeline()
        }
        function onSearchReady(repoPath, results) {
            if (!GitBridge || repoPath !== GitBridge.repoPath) return
            if (!root.searchMode) return  // 已退出搜索,丢弃过期搜索结果
            root.allCommits = results
            rebuildTimeline()
        }
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
                "hash": c.hash,
                "commit": c
            })
        }
        root.timelineItems = groups
    }

    Connections {
        target: GitBridge
        function onStatusChanged() { root.resetAndLoad() }
        function onRepoPathChanged(path) { root.resetForRepoChange() }
    }

    function _op(res) {
        if (res[0]) {
            Fluent.NotificationManager.toast.success(root, "成功", res[1] || "操作完成")
            root.resetAndLoad()
        } else {
            Fluent.NotificationManager.toast.error(root, "失败", res[1] || "操作失败")
        }
    }

    // 弹 reset 危险确认(按模式给不同说明,hard 额外强警告)
    function _askReset(mode) {
        if (!root.selectedCommit) return
        var desc = {
            "soft": "(soft 模式:保留暂存区和工作区的所有改动,仅移动 HEAD)",
            "mixed": "(mixed 模式:保留工作区改动,清空暂存区)",
            "hard": "⚠️ (hard 模式:丢弃工作区和暂存区的所有未提交改动,不可恢复!)"
        }[mode]
        resetDanger.content = "将回滚到提交 " + root.selectedCommit.shortHash
            + "\n" + desc + "\n此操作会改变提交历史。"
        resetDanger._hash = root.selectedCommit.hash
        resetDanger._mode = mode
        resetDanger.start()
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

                // 提交时间线(虚拟滚动,Timeline 自身 ListView 滚动+只渲染可见项,大列表不卡)
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    Fluent.Timeline {
                        anchors.fill: parent
                        virtualized: true
                        items: root.timelineItems
                        selectedRole: "hash"
                        selectedKey: root.selectedCommit ? root.selectedCommit.hash : undefined
                        onCardClickedData: function(groupIndex, cardIndex, cardData) {
                            if (cardData && cardData.commit)
                                root.selectedCommit = cardData.commit
                        }
                        onReachedEnd: {
                            if (!root.loading && root.hasMore && !root.searchMode)
                                root.loadMore()
                        }
                    }

                    // 加载状态提示(底部浮层)
                    Text {
                        anchors.bottom: parent.bottom
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottomMargin: Fluent.Enums.spacing.s
                        visible: root.loading
                        text: "加载中..."
                        color: Fluent.Enums.textColor.tertiary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.caption
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
                    anchors.margins: Fluent.Enums.spacing.xl
                    spacing: Fluent.Enums.spacing.l
                    visible: !!root.selectedCommit

                    // ── 头部:作者头像 + 提交标题 ──
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Fluent.Enums.spacing.m

                        Fluent.Avatar {
                            size: 44
                            text: root.selectedCommit ? root.selectedCommit.author : ""
                            Layout.alignment: Qt.AlignTop
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.xs
                            Text {
                                Layout.fillWidth: true
                                text: root.selectedCommit ? root.selectedCommit.message : ""
                                color: Fluent.Enums.textColor.primary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.title
                                font.bold: true
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                Layout.fillWidth: true
                                text: root.selectedCommit ? root.selectedCommit.author : ""
                                color: Fluent.Enums.textColor.secondary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.bodySmall
                            }
                        }
                    }

                    Fluent.Separator { Layout.fillWidth: true }

                    // ── 元信息:图标 + 标签 + 值 ──
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Fluent.Enums.spacing.m

                        // Hash(等宽,可点复制)
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.s
                            Fluent.Icon { icon: Fluent.Enums.icon.code; size: 16; color: Fluent.Enums.textColor.tertiary; Layout.alignment: Qt.AlignVCenter }
                            Text {
                                Layout.fillWidth: true
                                text: root.selectedCommit ? root.selectedCommit.hash : ""
                                color: Fluent.Enums.textColor.secondary
                                font.family: "Consolas, monospace"
                                font.pixelSize: Fluent.Enums.typography.bodySmall
                                elide: Text.ElideRight
                            }
                        }
                        // 作者邮箱
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.s
                            Fluent.Icon { icon: Fluent.Enums.icon.person; size: 16; color: Fluent.Enums.textColor.tertiary; Layout.alignment: Qt.AlignVCenter }
                            Text {
                                Layout.fillWidth: true
                                text: root.selectedCommit ? (root.selectedCommit.email || root.selectedCommit.author) : ""
                                color: Fluent.Enums.textColor.secondary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.bodySmall
                                elide: Text.ElideRight
                            }
                        }
                        // 时间
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.s
                            Fluent.Icon { icon: Fluent.Enums.icon.clock; size: 16; color: Fluent.Enums.textColor.tertiary; Layout.alignment: Qt.AlignVCenter }
                            Text {
                                Layout.fillWidth: true
                                text: root.selectedCommit ? root.selectedCommit.date : ""
                                color: Fluent.Enums.textColor.secondary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.bodySmall
                            }
                        }
                        // 分支(有才显示,用 Tag)
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.s
                            visible: root.selectedCommit && root.selectedCommit.branch !== ""
                            Fluent.Icon { icon: Fluent.Enums.icon.branch; size: 16; color: Fluent.Enums.textColor.tertiary; Layout.alignment: Qt.AlignVCenter }
                            Fluent.Tag {
                                status: Fluent.Enums.statusLevel.info
                                text: root.selectedCommit ? root.selectedCommit.branch : ""
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }

                    Fluent.Separator { Layout.fillWidth: true }

                    // ── 操作区 ──
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Fluent.Enums.spacing.m

                        // 常规操作:自然宽度左对齐(不铺满,更精致),风格统一
                        Flow {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.s
                            Fluent.Button {
                                text: "Checkout"
                                icon: Fluent.Enums.icon.checkmark_circle
                                onClicked: root._op(GitBridge.checkoutCommit(root.selectedCommit.hash))
                            }
                            Fluent.Button {
                                text: "Cherry-pick"
                                icon: Fluent.Enums.icon.branch
                                onClicked: root._op(GitBridge.cherryPick(root.selectedCommit.hash))
                            }
                            Fluent.Button {
                                text: "Revert"
                                icon: Fluent.Enums.icon.arrow_undo
                                onClicked: root._op(GitBridge.revertCommit(root.selectedCommit.hash))
                            }
                        }

                        Fluent.Separator { Layout.fillWidth: true }

                        // 辅助(左,轻量文字按钮) + 危险操作(右,强调)
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.xs
                            Fluent.Button {
                                text: "复制 Hash"
                                icon: Fluent.Enums.icon.copy
                                style: Fluent.Enums.button.style_transparent
                                onClicked: if (root.selectedCommit && ClipboardHelper) ClipboardHelper.copy(root.selectedCommit.hash)
                            }
                            Fluent.Button {
                                text: "详情"
                                icon: Fluent.Enums.icon.code
                                style: Fluent.Enums.button.style_transparent
                                onClicked: if (root.selectedCommit) commitDetailDialog.openFor(root.selectedCommit.hash)
                            }
                            Item { Layout.fillWidth: true }
                            Fluent.Button {
                                text: "Reset"
                                icon: Fluent.Enums.icon.arrow_clockwise
                                style: Fluent.Enums.button.style_primary
                                // 下拉选 reset 模式;选任一模式都走危险确认(hard 额外警告)
                                feature: Fluent.Enums.button.feature_dropdown
                                menuItems: ["Soft — 保留暂存区+工作区", "Mixed — 保留工作区,清暂存区", "Hard — 丢弃所有改动"]
                                onClicked: root._askReset("mixed")   // 主按钮默认 mixed(最常用)
                                onMenuItemClicked: function(index, text) {
                                    root._askReset(index === 0 ? "soft" : (index === 2 ? "hard" : "mixed"))
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // 危险操作:reset 二次确认(mode 由调用方经 _askReset 设置)
    DangerDialog {
        id: resetDanger
        title: "确认 Reset"
        countdown: 3
        property string _hash: ""
        property string _mode: "mixed"
        onConfirmed: root._op(GitBridge.resetToCommit(_hash, _mode))
    }

    // 提交详情
    CommitDetailDialog { id: commitDetailDialog }

    // 引用日志
    ReflogDialog {
        id: reflogDialog
        onCheckoutRequested: function(h) { root._op(GitBridge.checkoutCommit(h)) }
    }
}
