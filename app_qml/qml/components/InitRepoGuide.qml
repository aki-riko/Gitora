// 初始化仓库引导(阶段 4:迁移 init_repo_guide.py,基于 GuideShell)
// 4 步:欢迎 / 用户信息 / 远程仓库(可选) / 完成
import QtQuick
import QtQuick.Layouts

import FluentQML as Fluent

GuideShell {
    id: guide

    // 仓库路径(初始化目标),由外部设置
    property string repoPath: ""
    signal completed(string repoPath)

    // 收集的输入状态
    property string userName: ""
    property string userEmail: ""
    property string remoteName: "origin"
    property string remoteUrl: ""

    stepTitles: ["欢迎", "用户信息", "远程仓库", "完成"]
    finishText: "开始使用"

    // 进入用户信息页时预填全局配置
    onPageChanged: function(index) {
        if (index === 1 && guide.userName === "" && GitBridge) {
            var info = GitBridge.getUserInfo()
            guide.userName = info[0]
            guide.userEmail = info[1]
        }
    }

    onFinished: {
        // 保存用户信息(若填写)
        if (guide.userName && guide.userEmail)
            GitBridge.setUserInfo(guide.userName, guide.userEmail, false)
        // 添加远程(若填写)
        if (guide.remoteName && guide.remoteUrl)
            GitBridge.addRemote(guide.remoteName, guide.remoteUrl)
        guide.completed(guide.repoPath)
        guide.close()
    }

    pageComponents: [welcomePage, userInfoPage, remotePage, finalPage]

    // ---------- 第1步:欢迎 ----------
    property Component welcomePage: Component {
        Item {
            Column {
                anchors.centerIn: parent
                width: parent.width * 0.8
                spacing: Fluent.Enums.spacing.l
                Text {
                    text: "初始化 Git 仓库"
                    font.pixelSize: Fluent.Enums.typography.titleLarge
                    font.bold: true
                    color: Fluent.Enums.textColor.primary
                    font.family: Fluent.Enums.fontFamily
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                Text {
                    width: parent.width
                    text: "接下来将引导你完成:\n• 初始化本地仓库\n• 配置用户名和邮箱\n• 添加远程仓库(可选)"
                    color: Fluent.Enums.textColor.secondary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.body
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    // ---------- 第2步:用户信息 ----------
    property Component userInfoPage: Component {
        Item {
            Column {
                anchors.centerIn: parent
                width: parent.width * 0.7
                spacing: Fluent.Enums.spacing.l
                Text {
                    text: "配置用户信息"
                    font.pixelSize: Fluent.Enums.typography.subtitle
                    font.bold: true
                    color: Fluent.Enums.textColor.primary
                    font.family: Fluent.Enums.fontFamily
                }
                Text {
                    width: parent.width
                    text: "用于标识提交作者。留空则跳过此步。"
                    color: Fluent.Enums.textColor.tertiary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.caption
                    wrapMode: Text.WordWrap
                }
                Fluent.LineEdit {
                    width: parent.width
                    placeholderText: "用户名"
                    text: guide.userName
                    onTextChanged: guide.userName = text
                }
                Fluent.LineEdit {
                    width: parent.width
                    placeholderText: "邮箱"
                    text: guide.userEmail
                    onTextChanged: guide.userEmail = text
                }
            }
        }
    }

    // ---------- 第3步:远程仓库 ----------
    property Component remotePage: Component {
        Item {
            Column {
                anchors.centerIn: parent
                width: parent.width * 0.7
                spacing: Fluent.Enums.spacing.l
                Text {
                    text: "添加远程仓库"
                    font.pixelSize: Fluent.Enums.typography.subtitle
                    font.bold: true
                    color: Fluent.Enums.textColor.primary
                    font.family: Fluent.Enums.fontFamily
                }
                Text {
                    width: parent.width
                    text: "可选。留空则仅初始化本地仓库。"
                    color: Fluent.Enums.textColor.tertiary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.caption
                    wrapMode: Text.WordWrap
                }
                Fluent.LineEdit {
                    width: parent.width
                    placeholderText: "远程名称"
                    text: guide.remoteName
                    onTextChanged: guide.remoteName = text
                }
                Fluent.LineEdit {
                    width: parent.width
                    placeholderText: "远程 URL (https:// 或 git@...)"
                    text: guide.remoteUrl
                    onTextChanged: guide.remoteUrl = text
                }
            }
        }
    }

    // ---------- 第4步:完成 ----------
    property Component finalPage: Component {
        Item {
            Column {
                anchors.centerIn: parent
                width: parent.width * 0.8
                spacing: Fluent.Enums.spacing.l
                Fluent.Icon {
                    icon: Fluent.Enums.icon.checkmark_circle
                    iconSize: Fluent.Enums.iconSize.xl
                    color: Fluent.Enums.statusLevel.successColor
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                Text {
                    text: "准备就绪"
                    font.pixelSize: Fluent.Enums.typography.titleLarge
                    font.bold: true
                    color: Fluent.Enums.textColor.primary
                    font.family: Fluent.Enums.fontFamily
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                Text {
                    width: parent.width
                    text: "点击「开始使用」完成配置。"
                    color: Fluent.Enums.textColor.secondary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.body
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
