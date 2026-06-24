// 统一页面标题区(美化:统一各页标题排版与右侧操作区)
// 用法:
//   PageHeader {
//       title: "历史"; subtitle: "提交记录"
//       actions: [ Component{...} ]  // 或直接往 actionsContent 塞按钮
//   }
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

RowLayout {
    id: header
    property string title: ""
    property string subtitle: ""
    default property alias actionsContent: actionsRow.data

    Layout.fillWidth: true
    spacing: Fluent.Enums.spacing.l

    ColumnLayout {
        spacing: 0
        Text {
            text: header.title
            font.pixelSize: Fluent.Enums.typography.metric
            font.bold: true
            color: Fluent.Enums.textColor.primary
            font.family: Fluent.Enums.fontFamily
        }
        Text {
            visible: header.subtitle !== ""
            text: header.subtitle
            font.pixelSize: Fluent.Enums.typography.caption
            color: Fluent.Enums.textColor.tertiary
            font.family: Fluent.Enums.fontFamily
        }
    }

    Item { Layout.fillWidth: true }

    Row {
        id: actionsRow
        Layout.alignment: Qt.AlignVCenter
        spacing: Fluent.Enums.spacing.s
    }
}
