// 可复用 diff 查看器:文件摘要 + 统一/分栏视图 + 按文件过滤
// 渲染层为窗口化虚拟列表:只实例化可见行(± overscan),滚动零创建销毁。
// 行数据由 GitBridge.requestDiffRows 异步解析(app/common/diff_rows.py),
// 含词级高亮与语法着色段;旧的大 HTML 表格渲染已移除。
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Item {
    id: root

    property string rawDiff: ""
    property string filterPath: ""
    property bool loading: false
    property string loadingText: "加载中..."
    property string emptyText: "无差异"
    readonly property int lineNumberHorizontalPadding: Fluent.Enums.spacing.none
    readonly property int contentHorizontalPadding: Fluent.Enums.spacing.xs
    signal filterChanged(string path)

    // ---- 行模型(异步) ----
    property var _allRows: []
    property var _files: []
    property var _viewRows: []
    property var _pool: []
    property int _maxDigits: 3
    property real _contentWidth: 0
    readonly property int _overscanRows: 12
    readonly property int _poolSlack: 24
    readonly property real charWidth: monoMetrics.advanceWidth("0")
    readonly property int rowHeight: Math.ceil(monoMetrics.height) + 2
    readonly property real lineNoWidth: _maxDigits * charWidth + 2 * lineNumberHorizontalPadding + 10

    readonly property var rowColors: {
        var isDark = (typeof ThemeManager !== "undefined") && ThemeManager.isDark
        return {
            add: isDark ? "#4ec97a" : "#1a7f37",
            del: isDark ? "#f47067" : "#cf222e",
            hunk: isDark ? "#6cb6ff" : "#0969da",
            meta: isDark ? "#8b949e" : "#6e7781",
            normal: isDark ? "#d0d0d0" : "#24292f",
            ctx: isDark ? "#99a3ad" : "#4b535d",
            lineNo: isDark ? "#6e7a86" : "#8c959f",
            addBg: isDark ? "#17351f" : "#dafbe1",
            delBg: isDark ? "#3a1d21" : "#ffebe9",
            // 分区底色带:不透明预混色(半透明在 Mica 透明窗口/无合成环境会发黑)
            hunkBg: isDark ? "#1d2733" : "#e8f0fe",
            fileBg: isDark ? "#272e37" : "#eef1f4",
            kw: isDark ? "#ff7b72" : "#cf222e",
            str: isDark ? "#a5d6ff" : "#0a3069",
            com: isDark ? "#8b949e" : "#6e7781",
            num: isDark ? "#79c0ff" : "#0550ae",
            // 词级高亮底色:不透明,直接盖在行底色上形成清晰高亮块
            wordAdd: isDark ? "#2a6f37" : "#b7ecc4",
            wordDel: isDark ? "#7a2e2e" : "#ffc9c5"
        }
    }

    FontMetrics {
        id: monoMetrics
        font.family: "Consolas, Cascadia Code, monospace"
        font.pixelSize: 13
    }

    ListModel { id: fileModel }

    function clearDiff() {
        root.rawDiff = ""
        root.filterPath = ""
        root.loading = false
        fileModel.clear()
        root._applyRows([], [])
    }

    function setLoading(text) {
        root.loadingText = text || "加载中..."
        root.loading = true
    }

    function setDiff(rawDiff, filterPath) {
        root.rawDiff = rawDiff || ""
        root.filterPath = filterPath || ""
        root.loading = false
        // 相同（或同为空）字符串再次赋值不会触发属性变化信号，必须显式刷新。
        root._reloadFileModel()
        root._requestRows()
    }

    function _setFilter(path) {
        root.filterPath = path || ""
        root.filterChanged(root.filterPath)
    }

    function _reloadFileModel() {
        fileModel.clear()
        if (!GitBridge || !root.rawDiff)
            return
        // 防御:与 _requestRows 同款存在性检查;QML 访问 QObject 缺失方法会抛 TypeError,
        // 一旦抛出会使 setDiff → _requestRows 整链中断,行数据不加载。
        if (GitBridge.parseDiffFiles === undefined)
            return
        var files = GitBridge.parseDiffFiles(root.rawDiff) || []
        for (var i = 0; i < files.length; i++)
            fileModel.append(files[i])
    }

    // ---- 行数据获取 ----
    function _requestRows() {
        if (!root.rawDiff) {
            root._applyRows([], [])
            return
        }
        if (typeof GitBridge !== "undefined" && GitBridge && GitBridge.requestDiffRows) {
            GitBridge.requestDiffRows(root.rawDiff)
            return
        }
        // 无桥环境回退:仅分类行,无词级/语法着色
        root._applyRows(root._fallbackRows(root.rawDiff), [])
    }

    function _applyRows(rows, files) {
        root._allRows = rows || []
        root._files = files || []
        root._recompute()
    }

    function _fallbackRows(raw) {
        var rows = []
        var o = 0
        var n = 0
        var fi = -1
        var lines = raw.split("\n")
        for (var i = 0; i < lines.length; i++) {
            var ln = lines[i]
            if (ln.indexOf("diff ") === 0) {
                fi++
                rows.push({ t: "file", o: -1, n: -1, x: ln, fi: fi })
                o = 0
                n = 0
                continue
            }
            if (fi < 0 || ln.indexOf("@@") === 0) {
                if (fi < 0) {
                    rows.push({ t: "meta", o: -1, n: -1, x: ln, fi: 0 })
                    continue
                }
                var match = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(ln)
                if (match) {
                    o = parseInt(match[1])
                    n = parseInt(match[2])
                }
                rows.push({ t: "hunk", o: -1, n: -1, x: ln, fi: fi })
                continue
            }
            if (root._isFileMeta(ln)) {
                rows.push({ t: "meta", o: -1, n: -1, x: ln, fi: fi })
            } else if (ln.charAt(0) === "+") {
                rows.push({ t: "add", o: -1, n: n++, x: ln.substring(1), fi: fi })
            } else if (ln.charAt(0) === "-") {
                rows.push({ t: "del", o: o++, n: -1, x: ln.substring(1), fi: fi })
            } else if (ln.charAt(0) === " ") {
                rows.push({ t: "ctx", o: o++, n: n++, x: ln.substring(1), fi: fi })
            } else if (ln !== "") {
                rows.push({ t: "meta", o: -1, n: -1, x: ln, fi: fi })
            }
        }
        return rows
    }

    function _isFileMeta(line) {
        return line.indexOf("+++") === 0 || line.indexOf("---") === 0
            || line.indexOf("index ") === 0
            || line.indexOf("new file mode") === 0 || line.indexOf("deleted file mode") === 0
            || line.indexOf("rename from ") === 0 || line.indexOf("rename to ") === 0
    }

    // ---- 过滤与视图行构建 ----
    function _filteredRows() {
        var rows = root._allRows
        if (!root.filterPath)
            return rows
        var target = -1
        for (var i = 0; i < root._files.length; i++) {
            var f = root._files[i]
            if (f.path === root.filterPath || f.old_path === root.filterPath
                    || f.new_path === root.filterPath) {
                target = i
                break
            }
        }
        if (target < 0)
            return []  // 与旧 filter_unified_diff 未命中返回空一致
        var out = []
        for (i = 0; i < rows.length; i++)
            if (rows[i].fi === target)
                out.push(rows[i])
        return out
    }

    // 折叠纯噪音的文件元信息行(index/---/+++ 等),文件头行保留并展示为文件带。
    // 语义信息(rename/Binary/No newline/截断横幅)原样保留。
    function _collapseFileMeta(rows) {
        var out = []
        for (var i = 0; i < rows.length; i++) {
            var r = rows[i]
            if (r.t === "meta") {
                var x = r.x
                if (x.indexOf("index ") === 0 || x.indexOf("--- ") === 0
                        || x.indexOf("+++ ") === 0 || x.indexOf("old mode") === 0
                        || x.indexOf("new mode") === 0 || x.indexOf("similarity ") === 0)
                    continue
            }
            out.push(r)
        }
        return out
    }

    function _recompute() {
        var rows = root._collapseFileMeta(root._filteredRows())
        root._viewRows = rows

        var digits = 3
        var maxLen = 0
        for (var i = 0; i < rows.length; i++) {
            maxLen = Math.max(maxLen, rows[i].x.length)
            if (rows[i].o > 0) digits = Math.max(digits, String(rows[i].o).length)
            if (rows[i].n > 0) digits = Math.max(digits, String(rows[i].n).length)
        }
        root._contentWidth = 2 * root.lineNoWidth
            + root.contentHorizontalPadding + maxLen * root.charWidth + 24
        root._maxDigits = digits
        root._syncWindow()
    }

    // ---- 渲染富文本(词级底色 + 语法着色段) ----
    function _escape(text) {
        return (text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }

    function rowTextDefaultColor(row) {
        var c = root.rowColors
        if (!row) return c.meta
        if (row.t === "add") return c.add
        if (row.t === "del") return c.del
        if (row.t === "hunk") return c.hunk
        if (row.t === "file") return c.normal
        if (row.t === "meta") return c.meta
        return c.ctx
    }

    // 文件头行展示为仓库相对路径(取不到时回退原始 diff 行)
    function _fileDisplayText(row) {
        if (!row || row.t !== "file")
            return row ? row.x : ""
        var f = root._files[row.fi]
        if (f && (f.path || f.old_path || f.new_path))
            return f.path || f.new_path || f.old_path
        return (row.x || "").replace(/^diff --git a\/(\S+) b\/(\S+)$/, "$1")
    }

    function rowHtml(row) {
        if (!row)
            return ""
        var c = root.rowColors
        if (row.t === "file")
            return root._escape(root._fileDisplayText(row))
        var text = row.x || ""
        var seg = row.seg
        if (!seg || seg.length === 0)
            return root._escape(text)
        var out = ""
        for (var i = 0; i < seg.length; i++) {
            var s = seg[i][0]
            var e = seg[i][1]
            var fg = seg[i][2]
            var bg = seg[i][3]
            var piece = root._escape(text.substring(s, e))
            if (piece === "")
                continue
            var color = fg === "k" ? c.kw : fg === "s" ? c.str
                : fg === "c" ? c.com : fg === "n" ? c.num
                : root.rowTextDefaultColor(row)
            var style = "color:" + color
            if (bg === "a")
                style += ";background-color:" + c.wordAdd
            else if (bg === "d")
                style += ";background-color:" + c.wordDel
            out += '<span style="' + style + '">' + piece + '</span>'
        }
        return out
    }

    // ---- 窗口化虚拟渲染(delegate 池复用,滚动零创建销毁) ----
    function _syncWindow() {
        var total = root._viewRows.length
        var viewportH = Math.max(0, diffScrollArea.height)
        var cy = Math.max(0, root._scrollY)
        var first = 0
        var last = -1
        if (total > 0) {
            first = Math.max(0, Math.floor(cy / root.rowHeight) - root._overscanRows)
            last = Math.min(total - 1,
                Math.ceil((cy + viewportH) / root.rowHeight) + root._overscanRows)
        }
        var need = Math.max(0, last - first + 1)
        while (root._pool.length < need) {
            var created = rowDelegateComponent.createObject(canvas)
            if (created === null)
                break
            root._pool.push(created)
        }
        while (root._pool.length > need + root._poolSlack)
            root._pool.pop().destroy()
        for (var i = 0; i < root._pool.length; i++) {
            var item = root._pool[i]
            if (i < need) {
                item.visible = true
                item.y = (first + i) * root.rowHeight
                item.row = root._viewRows[first + i]
                item.viewer = root
            } else {
                item.visible = false
            }
        }
    }

    // ---- 摘要与旧接口保持一致 ----
    function _summaryText() {
        var additions = 0
        var deletions = 0
        for (var i = 0; i < fileModel.count; i++) {
            additions += fileModel.get(i).additions || 0
            deletions += fileModel.get(i).deletions || 0
        }
        var files = fileModel.count + " 文件"
        return files + "  +" + additions + "  -" + deletions
    }

    readonly property real _scrollY: diffScrollArea.contentY
    // 真实滚动视口宽(Flickable 已扣除纵向滚动条预留槽位)
    readonly property real _viewportWidth: diffScrollArea.flickableItem
        ? diffScrollArea.flickableItem.width : diffScrollArea.width
    on_ScrollYChanged: root._syncWindow()

    Component {
        id: rowDelegateComponent
        DiffRowDelegate {
            width: parent ? parent.width : 0
        }
    }

    Connections {
        target: typeof GitBridge !== "undefined" && GitBridge ? GitBridge : null
        function onDiffRowsReady(rawDiff, rowsJson) {
            if (rawDiff !== root.rawDiff)
                return  // 过期响应,丢弃(与提交详情对话框防过期同策略)
            var payload
            try {
                payload = JSON.parse(rowsJson || "{}")
            } catch (e) {
                payload = { files: [], rows: [] }
            }
            root._applyRows(payload.rows || [], payload.files || [])
        }
    }

    onRawDiffChanged: {
        root.loading = false
        root._reloadFileModel()
        root._requestRows()
    }
    onFilterPathChanged: root._recompute()

    ColumnLayout {
        anchors.fill: parent
        spacing: Fluent.Enums.spacing.s

        RowLayout {
            Layout.fillWidth: true
            spacing: Fluent.Enums.spacing.s

            Text {
                Layout.fillWidth: true
                text: fileModel.count > 0 ? root._summaryText() : ""
                color: Fluent.Enums.textColor.tertiary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
                elide: Text.ElideRight
            }
        }

        Fluent.ScrollArea {
            id: fileFilterScrollArea
            Layout.fillWidth: true
            Layout.preferredHeight: fileModel.count > 1 ? 34 : 0
            visible: fileModel.count > 1
            orientation: Qt.Horizontal
            showScrollBar: false
            padding: 0

            Row {
                id: fileFilterRow
                spacing: Fluent.Enums.spacing.s
                Fluent.Button {
                    text: "全部"
                    style: root.filterPath === "" ? Fluent.Enums.button.style_primary : Fluent.Enums.button.style_transparent
                    onClicked: root._setFilter("")
                }
                Repeater {
                    model: fileModel
                    delegate: Fluent.Button {
                        text: model.path
                        style: root.filterPath === model.path ? Fluent.Enums.button.style_primary : Fluent.Enums.button.style_transparent
                        onClicked: root._setFilter(model.path)
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root._viewRows.length === 0
            text: root.loading ? root.loadingText : root.emptyText
            color: root.rowColors.meta
            padding: 10
            font.family: "Consolas, Cascadia Code, monospace"
            font.pixelSize: 13
        }

        Fluent.ScrollArea {
            id: diffScrollArea
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root._viewRows.length > 0
            orientation: Qt.Horizontal | Qt.Vertical
            padding: 0
            onHeightChanged: root._syncWindow()
            onWidthChanged: root._syncWindow()

            Item {
                id: canvas
                // 视口宽必须取 Flickable 实宽(已扣除纵向滚动条预留),
                // 用外层宽会恒比视口宽出滚动条槽,造成常驻假横向滚动条。
                width: Math.max(root._viewportWidth, root._contentWidth)
                height: root._viewRows.length * root.rowHeight
            }
        }
    }
}
