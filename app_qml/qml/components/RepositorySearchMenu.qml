import QtQuick

import PrismQML as Fluent

Fluent.PopupWindowCore {
    id: control
    objectName: "repositorySearchMenu"

    property var paths: []
    property var filteredPaths: []
    property var pathFormatter: null
    property bool loading: false
    property alias searchText: searchInput.text
    readonly property int filteredCount: filteredPaths.length
    readonly property real _resultAreaHeight: Math.min(
        Math.max(filteredCount, 1) * Fluent.Enums.comboBoxMetrics.itemHeight,
        Fluent.Enums.comboBoxMetrics.popupMaxHeight)

    signal pathSelected(string path)

    popupWidth: Fluent.Enums.controlSize.cardWidth + Fluent.Enums.spacing.xxxl * 4
    popupHeight: Fluent.Enums.comboBoxMetrics.searchBoxHeight
        + _resultAreaHeight
        + Fluent.Enums.comboBoxMetrics.popupPadding
    closeOnClickOutside: true
    useQtPopupWindow: true

    onPopupHeightChanged: {
        if (!isOpen || isClosing) return
        // PopupWindowCore 的动画裁切高度会保留打开时的值，动态缩放时需同步。
        stabilizeInteraction()
        _clipHeight = popupHeight
    }

    function _normalizedPaths(values) {
        if (!values) return []
        var normalized = []
        for (var i = 0; i < values.length; i++)
            normalized.push(String(values[i] || ""))
        return normalized
    }

    function _rebuildFilter() {
        var query = searchInput.text.trim().toLowerCase()
        var matches = []
        for (var i = 0; i < paths.length; i++) {
            var path = String(paths[i] || "")
            if (query.length === 0 || path.toLowerCase().indexOf(query) !== -1)
                matches.push(path)
        }
        filteredPaths = matches
        resultList.scrollToTop()
    }

    function _displayPath(path) {
        return pathFormatter ? pathFormatter(path) : path
    }

    function setPaths(values) {
        paths = _normalizedPaths(values)
    }

    function prepareForOpen(values) {
        searchInput.text = ""
        setPaths(values)
        focusTimer.restart()
    }

    function activateIndex(index) {
        if (index < 0 || index >= filteredPaths.length) return
        var selectedPath = filteredPaths[index]
        close()
        pathSelected(selectedPath)
    }

    onPathsChanged: _rebuildFilter()

    Timer {
        id: focusTimer
        interval: 0
        onTriggered: searchInput.forceActiveFocus()
    }

    Column {
        anchors.fill: parent

        Item {
            id: searchBox
            objectName: "repositorySearchBox"
            width: parent.width
            height: Fluent.Enums.comboBoxMetrics.searchBoxHeight

            Fluent.LineEdit {
                id: searchInput
                objectName: "repositorySearchInput"
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.m
                inputType: Fluent.Enums.input.type_search
                placeholderText: "搜索仓库路径"
                onTextChanged: control._rebuildFilter()
                onSearched: function(text) {
                    if (control.filteredCount === 1)
                        control.activateIndex(0)
                }
            }
        }

        Item {
            id: resultArea
            objectName: "repositorySearchResultArea"
            width: parent.width
            height: control._resultAreaHeight

            Fluent.ScrollArea {
                id: resultList
                objectName: "repositorySearchResultList"
                anchors.fill: parent
                visible: control.filteredCount > 0
                type: Fluent.Enums.scroll.type_list
                itemHeight: Fluent.Enums.comboBoxMetrics.itemHeight
                model: control.filteredPaths
                reuseItems: true
                bounceEnabled: false
                selectable: false
                padding: 0

                delegate: Fluent.MenuDelegate {
                    objectName: "repositorySearchResult-" + index
                    width: ListView.view ? ListView.view.width : control.popupWidth
                    text: control._displayPath(modelData)
                    icon: Fluent.Enums.icon.folder
                    onClicked: control.activateIndex(index)
                }
            }

            Text {
                id: emptyState
                objectName: "repositorySearchEmptyState"
                anchors.centerIn: parent
                visible: control.filteredCount === 0
                text: searchInput.text.trim().length > 0
                    ? "没有匹配的仓库"
                    : (control.loading ? "正在扫描磁盘..." : "暂无最近仓库")
                color: Fluent.Enums.textColor.tertiary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.body
            }
        }
    }
}
