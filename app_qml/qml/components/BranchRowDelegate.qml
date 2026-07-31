import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Item {
    id: control

    required property var rowData
    property bool menuPinned: false
    property int itemHeight:
        Fluent.Enums.controlSize.buttonHeight + Fluent.Enums.spacing.l * 2
    readonly property bool isSection: rowData.rowType === "section"
    readonly property string branchName: rowData.name || ""
    readonly property bool isCurrentBranch: !!rowData.isCurrent
    readonly property bool isRemoteBranch: !!rowData.isRemote

    signal primaryRequested(string branchName, bool isRemote, bool isCurrent)
    signal menuRequested(
        var anchor,
        var owner,
        string branchName,
        bool isRemote,
        bool isCurrent
    )

    objectName: isSection ? "branchSectionRow" : "branchRowDelegate"
    height: itemHeight

    function openMenu(anchor) {
        control.menuPinned = true
        control.menuRequested(
            anchor,
            control,
            control.branchName,
            control.isRemoteBranch,
            control.isCurrentBranch)
    }

    HoverHandler {
        id: rowHover
        enabled: !control.isSection
    }

    Text {
        anchors.left: parent.left
        anchors.leftMargin: Fluent.Enums.spacing.xs
        anchors.verticalCenter: parent.verticalCenter
        visible: control.isSection
        text: control.rowData.sectionTitle || ""
        color: Fluent.Enums.textColor.primary
        font.family: Fluent.Enums.fontFamily
        font.pixelSize: Fluent.Enums.typography.titleLarge
        font.bold: true
    }

    Fluent.Card {
        anchors.fill: parent
        visible: !control.isSection

        RowLayout {
            anchors.fill: parent
            spacing: Fluent.Enums.spacing.m
            Fluent.Icon {
                icon: Fluent.Enums.icon.branch_fork
                iconSize: Fluent.Enums.iconSize.l
                color: control.isCurrentBranch
                    ? Fluent.Enums.accentColor
                    : Fluent.Enums.textColor.tertiary
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Text {
                    text: control.branchName
                        + (control.isCurrentBranch ? "  (当前)" : "")
                    color: Fluent.Enums.textColor.primary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.body
                    font.bold: control.isCurrentBranch
                }
                Text {
                    Layout.fillWidth: true
                    text: {
                        if (control.isRemoteBranch) return "远程分支"
                        var parts = []
                        if (control.rowData.tracking)
                            parts.push("跟踪 " + control.rowData.tracking)
                        if (control.rowData.ahead > 0)
                            parts.push("↑" + control.rowData.ahead)
                        if (control.rowData.behind > 0)
                            parts.push("↓" + control.rowData.behind)
                        return parts.length > 0 ? parts.join("  ") : "本地分支"
                    }
                    color: Fluent.Enums.textColor.tertiary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.caption
                    elide: Text.ElideRight
                }
            }
            Loader {
                active: !control.isSection
                    && (rowHover.hovered || control.menuPinned)
                visible: active

                sourceComponent: RowLayout {
                    spacing: Fluent.Enums.spacing.xs

                    Fluent.Button {
                        id: primaryButton
                        property string branchName: control.branchName
                        objectName: control.isRemoteBranch
                            ? "remoteBranchActionButton"
                            : "localBranchActionButton"
                        text: control.isRemoteBranch ? "获取并检出"
                            : (control.isCurrentBranch ? "管理" : "切换")
                        onClicked: {
                            if (control.isCurrentBranch) {
                                control.openMenu(primaryButton)
                            } else {
                                control.primaryRequested(
                                    control.branchName,
                                    control.isRemoteBranch,
                                    control.isCurrentBranch)
                            }
                        }
                    }

                    Fluent.Button {
                        id: moreButton
                        property string branchName: control.branchName
                        objectName: "branchMoreButton"
                        visible: !control.isCurrentBranch
                        icon: Fluent.Enums.icon.more_horizontal
                        toolTipText: "更多操作"
                        onClicked: control.openMenu(moreButton)
                    }
                }
            }
        }
    }
}
