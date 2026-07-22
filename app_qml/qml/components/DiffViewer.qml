// 可复用 diff 查看器:文件摘要 + 统一/分栏视图 + 按文件过滤
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Item {
    id: root

    property string rawDiff: ""
    property string filterPath: ""
    property string displayMode: "unified"
    property bool loading: false
    property string loadingText: "加载中..."
    property string emptyText: "无差异"
    signal filterChanged(string path)

    ListModel { id: fileModel }

    function clearDiff() {
        root.rawDiff = ""
        root.filterPath = ""
        root.loading = false
        fileModel.clear()
        diffArea.text = ""
    }

    function setLoading(text) {
        root.loadingText = text || "加载中..."
        root.loading = true
        diffArea.text = root._stateHtml(root.loadingText)
    }

    function _setFilter(path) {
        root.filterPath = path || ""
        root.filterChanged(root.filterPath)
    }

    function _reloadFileModel() {
        fileModel.clear()
        if (!GitBridge || !root.rawDiff)
            return
        var files = GitBridge.parseDiffFiles(root.rawDiff) || []
        for (var i = 0; i < files.length; i++)
            fileModel.append(files[i])
    }

    function _activeDiff() {
        if (!root.rawDiff)
            return ""
        if (!root.filterPath)
            return root.rawDiff
        if (GitBridge && GitBridge.filterDiffByPath)
            return GitBridge.filterDiffByPath(root.rawDiff, root.filterPath)
        return root.rawDiff
    }

    function _rebuild() {
        if (root.loading) {
            diffArea.text = root._stateHtml(root.loadingText)
            return
        }
        var diff = root._activeDiff()
        if (!diff) {
            diffArea.text = root._stateHtml(root.emptyText)
            return
        }
        diffArea.text = root.displayMode === "split" ? root._sideBySideHtml(diff) : root._unifiedHtml(diff)
    }

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

    function _escape(text) {
        return (text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }

    function _colors() {
        var isDark = (typeof ThemeManager !== "undefined") && ThemeManager.isDark
        return {
            add: isDark ? "#4ec97a" : "#1a7f37",
            del: isDark ? "#f47067" : "#cf222e",
            hunk: isDark ? "#6cb6ff" : "#0969da",
            meta: isDark ? "#8b949e" : "#6e7781",
            normal: isDark ? "#d0d0d0" : "#24292f",
            lineNo: isDark ? "#8b949e" : "#6e7781",
            addBg: isDark ? "#17351f" : "#dafbe1",
            delBg: isDark ? "#3a1d21" : "#ffebe9"
        }
    }

    function _stateHtml(text) {
        var c = root._colors()
        return '<div style="font-family:Consolas,monospace;color:' + c.meta + ';padding:10px">'
            + root._escape(text) + '</div>'
    }

    function _isFileMeta(line) {
        return line.indexOf("+++") === 0 || line.indexOf("---") === 0
            || line.indexOf("diff ") === 0 || line.indexOf("index ") === 0
            || line.indexOf("new file mode") === 0 || line.indexOf("deleted file mode") === 0
            || line.indexOf("rename from ") === 0 || line.indexOf("rename to ") === 0
    }

    function _tableStart() {
        return '<table cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-family:Consolas,monospace;font-size:12px">'
    }

    function _numCell(value, color) {
        return '<td width="1" style="color:' + color + ';text-align:right;padding:0 8px;white-space:pre">'
            + (value === "" ? "&nbsp;" : value) + '</td>'
    }

    function _textCell(text, color, bg) {
        return '<td style="color:' + color + ';background:' + bg
            + ';white-space:pre;padding:0 8px">' + root._escape(text) + '</td>'
    }

    // Qt 富文本的自动表格布局会把 colspan 文件头宽度平均分给行号列，
    // 导致正文被推到视口中后部。元信息也使用与正文相同的显式列结构。
    function _unifiedMetaRow(text, color, lineColor) {
        return "<tr>" + root._numCell("", lineColor) + root._numCell("", lineColor)
            + root._textCell(text, color, "transparent") + "</tr>"
    }

    // 分栏元信息不参与四列正文的宽度计算，否则长文件路径会把两侧代码推得很远。
    function _splitMetaRow(text, color) {
        return '</table><div style="color:' + color + ';white-space:pre;padding:0 8px">'
            + root._escape(text) + '</div>' + root._tableStart()
    }

    function _unifiedHtml(raw) {
        var c = root._colors()
        var lines = raw.split("\n")
        var html = [root._tableStart()]
        var oldNo = 0
        var newNo = 0
        for (var i = 0; i < lines.length; i++) {
            var ln = lines[i]
            var match = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(ln)
            if (match) {
                oldNo = parseInt(match[1])
                newNo = parseInt(match[2])
                html.push(root._unifiedMetaRow(ln, c.hunk, c.lineNo))
            } else if (root._isFileMeta(ln)) {
                html.push(root._unifiedMetaRow(ln, c.meta, c.lineNo))
            } else if (ln.charAt(0) === "+") {
                html.push("<tr>" + root._numCell("", c.lineNo) + root._numCell(newNo++, c.lineNo)
                    + root._textCell(ln, c.add, c.addBg) + "</tr>")
            } else if (ln.charAt(0) === "-") {
                html.push("<tr>" + root._numCell(oldNo++, c.lineNo) + root._numCell("", c.lineNo)
                    + root._textCell(ln, c.del, c.delBg) + "</tr>")
            } else if (ln.charAt(0) === " ") {
                html.push("<tr>" + root._numCell(oldNo++, c.lineNo) + root._numCell(newNo++, c.lineNo)
                    + root._textCell(ln, c.normal, "transparent") + "</tr>")
            } else if (ln !== "") {
                html.push(root._unifiedMetaRow(ln, c.meta, c.lineNo))
            }
        }
        html.push("</table>")
        return html.join("")
    }

    function _sideBySideHtml(raw) {
        var c = root._colors()
        var lines = raw.split("\n")
        var html = [root._tableStart()]
        var oldNo = 0
        var newNo = 0
        for (var i = 0; i < lines.length; i++) {
            var ln = lines[i]
            var match = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(ln)
            if (match) {
                oldNo = parseInt(match[1])
                newNo = parseInt(match[2])
                html.push(root._splitMetaRow(ln, c.hunk))
            } else if (root._isFileMeta(ln)) {
                html.push(root._splitMetaRow(ln, c.meta))
            } else if (ln.charAt(0) === "-") {
                var deleted = []
                var added = []
                while (i < lines.length && lines[i].charAt(0) === "-" && !root._isFileMeta(lines[i])) {
                    deleted.push(lines[i].substring(1))
                    i++
                }
                while (i < lines.length && lines[i].charAt(0) === "+" && !root._isFileMeta(lines[i])) {
                    added.push(lines[i].substring(1))
                    i++
                }
                i--
                var maxRows = Math.max(deleted.length, added.length)
                for (var row = 0; row < maxRows; row++) {
                    var leftNo = row < deleted.length ? oldNo++ : ""
                    var rightNo = row < added.length ? newNo++ : ""
                    var leftText = row < deleted.length ? deleted[row] : ""
                    var rightText = row < added.length ? added[row] : ""
                    html.push("<tr>" + root._numCell(leftNo, c.lineNo) + root._textCell(leftText, c.del, c.delBg)
                        + root._numCell(rightNo, c.lineNo) + root._textCell(rightText, c.add, c.addBg) + "</tr>")
                }
            } else if (ln.charAt(0) === "+") {
                html.push("<tr>" + root._numCell("", c.lineNo) + root._textCell("", c.normal, "transparent")
                    + root._numCell(newNo++, c.lineNo) + root._textCell(ln.substring(1), c.add, c.addBg) + "</tr>")
            } else if (ln.charAt(0) === " ") {
                var text = ln.substring(1)
                html.push("<tr>" + root._numCell(oldNo++, c.lineNo) + root._textCell(text, c.normal, "transparent")
                    + root._numCell(newNo++, c.lineNo) + root._textCell(text, c.normal, "transparent") + "</tr>")
            } else if (ln !== "") {
                html.push(root._splitMetaRow(ln, c.meta))
            }
        }
        html.push("</table>")
        return html.join("")
    }

    onRawDiffChanged: {
        root.loading = false
        root._reloadFileModel()
        root._rebuild()
    }
    onFilterPathChanged: root._rebuild()
    onDisplayModeChanged: root._rebuild()
    onLoadingChanged: root._rebuild()

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
            Fluent.Button {
                text: "统一"
                style: root.displayMode === "unified" ? Fluent.Enums.button.style_primary : Fluent.Enums.button.style_transparent
                onClicked: root.displayMode = "unified"
            }
            Fluent.Button {
                text: "分栏"
                style: root.displayMode === "split" ? Fluent.Enums.button.style_primary : Fluent.Enums.button.style_transparent
                onClicked: root.displayMode = "split"
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

        Fluent.ScrollArea {
            id: diffScrollArea
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal | Qt.Vertical
            padding: 0

            TextEdit {
                id: diffArea
                width: Math.max(parent ? parent.width : 0, paintedWidth)
                height: Math.max(1, paintedHeight)
                readOnly: true
                selectByMouse: true
                textFormat: TextEdit.RichText
                wrapMode: TextEdit.NoWrap
                font.family: "Consolas, Cascadia Code, monospace"
                font.pixelSize: Fluent.Enums.typography.caption
                color: Fluent.Enums.textColor.primary
                text: ""
            }
        }
    }
}
