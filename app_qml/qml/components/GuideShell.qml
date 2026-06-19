// GuideShell - 分步引导窗外壳(替代 QFW Pro 的 GuideWindow)
// 组合:WindowsCore(Fluent 窗口壳) + Stepper(顶部步骤) + StackedWidget(翻页) + 底部导航按钮
//
// 用法:
//   GuideShell {
//       stepTitles: ["欢迎", "用户信息", "远程", "完成"]
//       pages: [Component{...}, ...]  // 或直接塞子项
//       onFinished: { ... }
//       onPageChanged: (index) => { ... }  // 翻页时校验
//   }
import QtQuick

import FluentQML as Fluent

Fluent.WindowsCore {
    id: shell

    // ==================== 公开属性 ====================
    property var stepTitles: []                  // 步骤标题数组
    property alias pageComponents: stack.pageComponents  // Component 列表(推荐)
    property int currentIndex: 0
    readonly property int count: stepTitles.length
    readonly property bool isLastPage: currentIndex >= count - 1
    readonly property bool isFirstPage: currentIndex <= 0

    property string nextText: "下一步"
    property string backText: "上一步"
    property string finishText: "完成"

    // ==================== 信号 ====================
    signal finished()                  // 最后一页点"完成"
    signal pageChanged(int index)      // 翻页(校验时机)

    width: 800
    height: 520
    windowColor: Fluent.Enums.backgroundColor
    visible: false   // 默认隐藏,仅在 show() 时显示(否则作为子项声明会自动弹出)

    onCurrentIndexChanged: pageChanged(currentIndex)

    function goNext() {
        if (isLastPage) { finished() }
        else { currentIndex++ }
    }
    function goBack() {
        if (!isFirstPage) currentIndex--
    }

    // ==================== 布局 ====================
    Column {
        anchors.fill: parent
        anchors.margins: Fluent.Enums.spacing.xl
        spacing: Fluent.Enums.spacing.l

        // 顶部步骤指示
        Fluent.Stepper {
            id: stepper
            width: parent.width
            steps: shell.stepTitles
            currentStep: shell.currentIndex
        }

        // 中间翻页容器
        Fluent.StackedWidget {
            id: stack
            width: parent.width
            height: parent.height - stepper.height - footer.height - parent.spacing * 2
            currentIndex: shell.currentIndex
        }

        // 底部导航按钮
        Row {
            id: footer
            width: parent.width
            spacing: Fluent.Enums.spacing.m
            layoutDirection: Qt.RightToLeft

            Fluent.Button {
                text: shell.isLastPage ? shell.finishText : shell.nextText
                style: Fluent.Enums.button.style_primary
                onClicked: shell.goNext()
            }
            Fluent.Button {
                text: shell.backText
                visible: !shell.isFirstPage
                onClicked: shell.goBack()
            }
        }
    }
}
