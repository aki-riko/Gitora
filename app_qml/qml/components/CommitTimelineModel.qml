// 提交历史到 Timeline 图模式数据的转换模型
import QtQuick
import PrismQML as Fluent

QtObject {
    id: root

    property var commits: []
    readonly property var result: _buildResult(commits)
    readonly property var items: result.items
    readonly property int laneCount: result.laneCount

    function _dateGroup(dateStr) {
        var date = (dateStr || "").substring(0, 10)
        if (date === "") return "未知日期"
        var today = new Date()
        var pad = function(value) { return value < 10 ? "0" + value : "" + value }
        var todayText = today.getFullYear() + "-" + pad(today.getMonth() + 1)
            + "-" + pad(today.getDate())
        var yesterday = new Date(today.getTime() - 86400000)
        var yesterdayText = yesterday.getFullYear() + "-"
            + pad(yesterday.getMonth() + 1) + "-" + pad(yesterday.getDate())
        if (date === todayText) return "今天"
        if (date === yesterdayText) return "昨天"
        return date
    }

    function _refStatus(kind) {
        if (kind === "head") return Fluent.Enums.statusLevel.processing
        if (kind === "tag") return Fluent.Enums.statusLevel.warning
        if (kind === "remote") return Fluent.Enums.statusLevel.success
        return Fluent.Enums.statusLevel.info
    }

    function _labels(refs) {
        var labels = []
        var values = refs || []
        for (var index = 0; index < values.length; index++) {
            labels.push({
                "text": values[index].name || "",
                "status": _refStatus(values[index].kind || "ref")
            })
        }
        return labels
    }

    function _graphFor(commit) {
        var graph = commit.graph || {}
        if (graph.nodeLane !== undefined) return graph
        return {"nodeLane": 0, "nodeColorIndex": 0, "laneCount": 1, "segments": []}
    }

    function _cardFor(commit) {
        var isReverted = !!commit.revertedBy
        var relationText = ""
        if (commit.reverts)
            relationText += " · 撤销 " + commit.reverts.substring(0, 8)
        if (isReverted) relationText += " · 已撤销"
        return {
            "text": commit.message,
            "description": commit.shortHash + " · " + commit.author + relationText,
            "status": isReverted ? "warning" : "info",
            "strikeOut": isReverted,
            "hash": commit.hash,
            "labels": _labels(commit.refs),
            "graph": _graphFor(commit),
            "commit": commit
        }
    }

    function _buildResult(values) {
        var groups = []
        var indexByLabel = ({})
        var maximumLanes = 1
        for (var index = 0; index < values.length; index++) {
            var commit = values[index]
            var label = _dateGroup(commit.date)
            if (indexByLabel[label] === undefined) {
                indexByLabel[label] = groups.length
                groups.push({
                    "title": label,
                    "status": "info",
                    "graph": commit.graphHeader || {},
                    "cards": []
                })
            }
            var card = _cardFor(commit)
            maximumLanes = Math.max(maximumLanes, card.graph.laneCount || 1)
            groups[indexByLabel[label]].cards.push(card)
        }
        return {"items": groups, "laneCount": maximumLanes}
    }
}
