import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

// 表单型 MessageBox 必须将标题和表单放进同一个布局，避免同级子项重叠。
Fluent.Label {
    Layout.fillWidth: true
    type: Fluent.Enums.label.type_subtitle
    color: Fluent.Enums.textColor.primary
    wrapMode: Text.WordWrap
}
