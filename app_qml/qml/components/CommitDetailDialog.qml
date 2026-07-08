// 提交详情对话框(基于 DialogBoxCore 自定义,标题自绘避免与 MessageBox 自带 title 重叠)
// 只读展示:提交信息 + 变更文件列表 + 完整 diff
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.DialogBoxCore {
    id: dlg

    property string commitHash: ""
    property string _requestRepoPath: ""
    property string _author: ""
    property string _shortHash: ""
    property string _date: ""
    ListModel { id: filesModel }

    function clearContent() {
        dlg.commitHash = ""
        dlg._requestRepoPath = ""
        dlg._author = ""
        dlg._shortHash = ""
        dlg._date = ""
        msgLabel.text = ""
        filesModel.clear()
        diffArea.text = ""
    }

    function openFor(hash) {
        dlg.commitHash = hash
        dlg._requestRepoPath = (GitBridge && GitBridge.repoPath) ? GitBridge.repoPath : ""
        var d = GitBridge.getCommitDetail(hash) || ({})
        msgLabel.text = d.message || ""
        dlg._author = d.author || ""
        dlg._shortHash = d.shortHash || ""
        dlg._date = d.date || ""
        filesModel.clear()
        diffArea.text = "加载中..."
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
            diffArea.text = dlg._diffToHtml(diff || "")
        }
    }

    // diff 纯文本 -> 按行着色的 HTML(+绿/-红/@@蓝/文件头灰),与 RepoView 一致
    function _diffToHtml(raw) {
        if (!raw) return ""
        var isDark = (typeof ThemeManager !== "undefined") && ThemeManager.isDark
        var cAdd = isDark ? "#4ec97a" : "#1a7f37"
        var cDel = isDark ? "#f47067" : "#cf222e"
        var cHunk = isDark ? "#6cb6ff" : "#0969da"
        var cMeta = isDark ? "#8b949e" : "#8a8a8a"
        var cNormal = isDark ? "#d0d0d0" : "#1f1f1f"
        var lines = raw.split("\n")
        var out = []
        for (var i = 0; i < lines.length; i++) {
            var ln = lines[i]
            var esc = ln.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            if (esc === "") esc = "&nbsp;"
            var color = cNormal
            if (ln.indexOf("+++") === 0 || ln.indexOf("---") === 0 || ln.indexOf("diff ") === 0 || ln.indexOf("index ") === 0)
                color = cMeta
            else if (ln.indexOf("@@") === 0) color = cHunk
            else if (ln.charAt(0) === "+") color = cAdd
            else if (ln.charAt(0) === "-") color = cDel
            out.push('<span style="color:' + color + '">' + esc + '</span>')
        }
        return '<pre style="margin:0;font-family:Consolas,monospace">' + out.join("<br>") + '</pre>'
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
        width: 580
        spacing: Fluent.Enums.spacing.l

        // ── 头部:头像 + 消息标题 + 元信息 ──
        RowLayout {
            Layout.fillWidth: true
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
                    Layout.preferredHeight: Math.min(msgLabel.implicitHeight, 96)
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
            Layout.preferredHeight: Math.min(filesModel.count * 24 + 4, 110)
            padding: 0
            Column {
                // 绑 ScrollArea 自身宽度而非 parent:content 被塞进内部 Loader,
                // parent(contentHolder)在 Loader 实例化时序里会短暂为 null,
                // 读 parent.width 会报 "Cannot read property 'width' of null"。
                width: filesScrollArea.width
                Repeater {
                    model: filesModel
                    delegate: Row {
                        width: parent.width
                        height: 24
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

        Fluent.Separator { Layout.fillWidth: true }

        // ── diff ──(ScrollArea 自带平滑滚动条,外层 Rectangle 提供边框)
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 260
            radius: Fluent.Enums.radius.medium
            color: Fluent.Enums.cardColor
            border.width: Fluent.Enums.border.normal
            border.color: Fluent.Enums.stateColor.border
            Fluent.ScrollArea {
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.s
                padding: 0
                TextEdit {
                    id: diffArea
                    readOnly: true
                    selectByMouse: true
                    textFormat: TextEdit.RichText   // 按行着色的 HTML(+绿/-红/@@蓝)
                    wrapMode: TextEdit.NoWrap
                    font.family: "Consolas, monospace"
                    font.pixelSize: Fluent.Enums.typography.caption
                    color: Fluent.Enums.textColor.primary
                }
            }
        }
    }
}
