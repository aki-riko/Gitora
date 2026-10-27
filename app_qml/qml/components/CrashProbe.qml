// CrashProbe - 可选崩溃面包屑观测 Probe
// 仅在 GITORA_CRASH_TRACE=1 时由 main.qml 启用；关闭时直接 return，不拼字符串、不建定时器。
//
// 为什么需要它：2026-10-27 那次原生崩溃（qt6qml.dll+0x17131b，QV4 ordinaryToPrimitive
// 读空 internalClass）留下了 1.76GB 全内存转储，但 Gitora 日志在崩溃前 35 分钟一行都没有，
// 因为没有 QML 侧面包屑。QML 的 console 输出不会落进 Gitora 日志文件，所以必须经
// QmlRenderBridge.logCrashTrace（Python 侧仅在开关打开时落盘）写入。
//
// 判读方式：崩溃后看日志里最后几条 [CRASH_TRACE] 面包屑，即可还原崩溃前正在做哪类操作
// （窗口可见性变化 / 页面切换 / 标签页切换 / 差异视图重建），把范围收敛到具体视图。
// 面包屑只记录“事件名 + 关键数值”，不记录任何仓库内容、路径或用户数据。
//
// 注意：观测不是修复条件。排查结束后清理 GITORA_CRASH_TRACE 并完整重启应用。
import QtQuick

QtObject {
    id: probe

    // ==================== Public Props 公开属性 ====================
    property bool enabled: false
    // 经 main.qml 注入的渲染桥；只用其 logCrashTrace（Python 侧再做一次开关判定）。
    property var renderBridge: null
    // 面包屑序号上限保护：异常路径下高频事件不会无限增长日志。
    property int maxEvents: 2000

    // ==================== Readonly State 只读状态 ====================
    property int eventCount: 0
    property string lastEventText: ""
    // 供断言与外部观测读取：桥是否真的可用，避免“以为在观测其实没写盘”。
    readonly property bool bridged:
        probe.renderBridge !== null
        && typeof probe.renderBridge.logCrashTrace === "function"

    // 打开时打一行“已启用”，用来证明观测真的生效（而不是静默无输出）。
    onEnabledChanged: {
        if (probe.enabled)
            probe.mark("[CRASH_TRACE] armed bridged=" + probe.bridged
                + " maxEvents=" + probe.maxEvents)
    }

    // ==================== Public Methods 公开方法 ====================
    // 记一条面包屑。tag 是事件分类（短英文常量），detail 是可选补充文本。
    // 关闭或超限时立即返回，零分配、零日志。
    function mark(tag, detail) {
        if (!probe.enabled) return
        if (probe.eventCount >= probe.maxEvents) return
        probe.eventCount += 1
        var text = "[CRASH_TRACE] #" + probe.eventCount + " " + tag
        if (detail !== undefined && detail !== null && detail !== "")
            text += " " + detail
        probe.lastEventText = text
        if (probe.bridged)
            probe.renderBridge.logCrashTrace(text)
        else
            console.debug(text)
    }

    // 便捷包装：把布尔值转成稳定的 "0"/"1"，避免 undefined 混进日志。
    function markFlag(tag, name, value) {
        if (!probe.enabled) return
        probe.mark(tag, name + "=" + (value ? 1 : 0))
    }
}
