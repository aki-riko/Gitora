// StallTraceProbe - 可选主线程停顿观测 Probe
// 仅在 GITORA_STALL_TRACE=1 时由 main.qml 启用；关闭时不创建定时器、不做任何工作。
// 用途：把“长时间运行后点击/下拉响应奇慢”定位到主线程停顿，并同时记录当时的
// 进程顶层窗口数，用来区分「业务侧主线程被占满」与「引擎侧窗口/GPU 资源累积」。
import QtQuick

QtObject {
    id: probe

    // ==================== Public Props 公开属性 ====================
    property bool enabled: false
    property int intervalMs: 100
    property int thresholdMs: 250
    // 只读上下文来源：仓库忙碌状态与进程顶层窗口数（可为 null）
    property var gitBridge: null
    property var renderBridge: null

    // ==================== Readonly State 只读状态 ====================
    property double lastTickMs: 0
    property int stallCount: 0
    property string lastStallText: ""
    // 定时器实际是否在跑：供断言与外部观测读取，避免直接暴露 Timer 对象。
    readonly property bool ticking: tickTimer.running

    // 打开时打一行“已启用”，用来证明观测真的生效（而不是静默无输出）。
    onEnabledChanged: {
        if (probe.enabled)
            probe._emit("[STALL_TRACE] armed interval=" + probe.intervalMs
                + "ms threshold=" + probe.thresholdMs + "ms")
    }

    // ==================== Public Methods 公开方法 ====================
    // 返回本次打点的实际间隔（ms）；首次调用返回 0。
    // 间隔超过阈值时记一条停顿观测——这是“主线程被占住多久”的直接证据。
    function recordTick(nowMs) {
        var previous = probe.lastTickMs
        probe.lastTickMs = nowMs
        if (previous <= 0) return 0
        var gap = nowMs - previous
        if (gap < probe.thresholdMs) return gap
        probe.stallCount += 1
        probe._emit("[STALL_TRACE] #" + probe.stallCount
            + " t=" + nowMs
            + " gap=" + gap + "ms"
            + " interval=" + probe.intervalMs
            + " threshold=" + probe.thresholdMs
            + probe._contextText())
        return gap
    }

    // ==================== Internal Methods 内部方法 ====================
    // QML 的 console 输出不会落进 Gitora 日志文件，所以经桥写应用日志；
    // 桥不可用时退回 console，保证探针本身仍可独立使用。
    function _emit(message) {
        probe.lastStallText = message
        if (probe.renderBridge
                && typeof probe.renderBridge.logStallTrace === "function") {
            probe.renderBridge.logStallTrace(message)
            return
        }
        console.debug(message)
    }

    function _contextText() {
        var parts = []
        if (probe.gitBridge)
            parts.push("busy=" + probe.gitBridge.operationBusy)
        if (probe.renderBridge
                && typeof probe.renderBridge.topLevelWindowCount === "function")
            parts.push("windows=" + probe.renderBridge.topLevelWindowCount())
        return parts.length > 0 ? " " + parts.join(" ") : ""
    }

    // ==================== Content 内容 ====================
    property Timer tickTimer: Timer {
        interval: probe.intervalMs
        repeat: true
        running: probe.enabled
        triggeredOnStart: true
        onTriggered: probe.recordTick(Date.now())
    }
}
