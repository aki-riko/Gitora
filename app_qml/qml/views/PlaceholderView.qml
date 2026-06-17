// 占位页(阶段 0:历史/分支尚未迁移)
import QtQuick
import FluentQML as Fluent

Item {
    Text {
        anchors.centerIn: parent
        text: "此页面尚未迁移"
        color: Fluent.Enums.textColor.tertiary
        font.family: Fluent.Enums.fontFamily
        font.pixelSize: Fluent.Enums.typography.subtitle
    }
}
