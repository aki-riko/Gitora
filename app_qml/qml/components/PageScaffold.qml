// 页面脚手架(美化:统一各页的滚动+内容最大宽度+边距,消除超宽屏拉伸)
// 用法:
//   PageScaffold {
//       PageHeader { title: "..."; ... }
//       <页面内容,宽度用 contentWidth>
//   }
import QtQuick
import QtQuick.Layouts

import FluentQML as Fluent

Fluent.ScrollArea {
    id: scaffold

    // 内容最大宽度(超宽屏时居中,不无限拉伸)
    property int maxContentWidth: 980
    default property alias pageContent: contentColumn.data
    readonly property real contentWidth: contentColumn.width

    Item {
        width: scaffold.width
        // 高度由内容撑开(ScrollArea 需要)
        implicitHeight: contentColumn.implicitHeight + Fluent.Enums.spacing.xxl * 2

        ColumnLayout {
            id: contentColumn
            anchors.top: parent.top
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.topMargin: Fluent.Enums.spacing.xxl
            width: Math.min(scaffold.width - Fluent.Enums.spacing.xxl * 2, scaffold.maxContentWidth)
            spacing: Fluent.Enums.spacing.l
        }
    }
}
