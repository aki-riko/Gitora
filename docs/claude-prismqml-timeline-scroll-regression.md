# PrismQML Timeline 连续滚轮上下弹跳回归交接

> 这份文档用于交给 Claude 继续修复。目标是修复 Gitora 历史页使用 PrismQML `Timeline` 时的连续同向滚轮抖动，同时保留原有的超出滚动/回弹能力。

## 1. 用户实际描述

用户描述的现象不是普通的“松手后超出边界再回弹”：

> Git 历史列表在滚轮持续往上时，会在上下方向反复弹跳。

具体表现：滚轮仍然持续向同一个方向输入，列表不是单次越界后回到边界，而是在上下位置之间反复改写，像滚动目标被持续重启或被两个边界校正路径互相拉扯。

用户明确要求：

- 仍然允许超出滚动，不能简单关闭所有 overshoot/bounce。
- 只修复“连续同方向滚轮时上下反复抖动”的回归。
- 不要把问题误判为 Mica、普通松手回弹或 Git 历史数据刷新。

## 2. 真实日志证据

用户提供的日志文件：

`C:\Users\Kotori\.codex\attachments\e75046d6-fe18-4e13-b99f-d14b96129645\pasted-text.txt`

关键内容：

```text
00:16:04.229 [DEBUG] [Mica] Mica effect enabled reapplied (hwnd=126029472)
00:16:05.738 [DEBUG] [Updater] [Updater] 已是最新版本 v1.6.1
00:16:07.521 [WARNING] [QML] file:///D:/PrismQML/Gitora/app_qml/qml/views/HistoryView.qml:100: ReferenceError: historyTimeline is not defined
```

`historyTimeline is not defined` 随后约每 200ms 重复一次。

判断：

- Mica 和 Updater 日志只是同一时间段的普通启动日志，没有证据表明它们造成滚动抖动。
- `historyTimeline` 警告是历史页探针引用嵌套 QML `id` 的作用域错误。它需要单独修复，但不是“持续同向滚轮上下弹跳”的直接根因。
- 滚动抖动的根因应在 Timeline 虚拟 `ListView`、`SmoothScrollHelper`、动态 `originY/contentHeight` 重测和连续 wheel 输入的时序交互中查找。

## 3. Gitora 当前相关结构

历史页：

- [`app_qml/qml/views/HistoryView.qml`](../app_qml/qml/views/HistoryView.qml)
- 使用 `Fluent.Timeline`，`type: Fluent.Enums.timeline.type_graph`
- `virtualized: true`
- Timeline 内部对象名：`historyTimeline`
- 虚拟视口对象名：`timelineVirtualViewport`
- Timeline 通过自己的 `SmoothScrollHelper` 处理 wheel

当前历史页相关代码语义：

```qml
Fluent.Timeline {
    id: historyTimeline
    objectName: "historyTimeline"
    type: Fluent.Enums.timeline.type_graph
    virtualized: true
    items: root.renderedTimelineItems
}
```

当前 PrismQML Timeline 实现：

- [`prismqml/PrismQML/controls/containers/TimelineCore.qml`](../../PrismQML/prismqml/PrismQML/controls/containers/TimelineCore.qml)
- 虚拟列表：`QtQ.ListView { objectName: "timelineVirtualViewport" }`
- 虚拟列表当前历史基线是：`boundsBehavior: Flickable.DragAndOvershootBounds`
- 内置滚动助手当前历史基线是：`bounceEnabled: true`

Gitora 开发态已经改为优先加载同级本地 PrismQML 源码：

```text
D:\PrismQML\Gitora\app_qml\main_qml.py
D:\PrismQML\PrismQML\prismqml
```

Gitora 当前 `.venv` 的 PyPI 包仍是 `0.4.1.5`，但开发态启动入口会优先导入本地 `D:\PrismQML\PrismQML` 源码。该指向变更提交为：

```text
6631cc2 fix: 开发态优先使用本地 PrismQML
```

## 4. 已确认的 PrismQML 历史线索

### 4.1 Timeline 专用历史修复

提交 `7acfd4217`：

```text
fix(Timeline): 关闭虚拟时间线回弹,修复顶部超滑闪烁(v0.2.24.5)
```

该提交明确记录了旧问题：

- 虚拟 Timeline 的 `SmoothScrollHelper` 默认开启回弹。
- 驱动的 ListView 使用 `StopAtBounds`。
- helper 把 `contentY` 写成越界负值做回弹动画。
- Flickable 又逐帧把 `contentY` 夹回边界。
- 两条路径互相对抗，导致 `contentY` 在边界值和越界值之间抖动。

该修复当时使用：

```qml
boundsBehavior: Flickable.StopAtBounds
bounceEnabled: false
```

注意：这条历史修复说明了抖动机制，但用户现在明确要求保留超出滚动。因此不能直接照搬为最终方案，只能作为根因证据和对照基线。

### 4.2 引入回归的 Timeline 改动

提交 `82e48a07b`：

```text
fix: 恢复时间线边界回弹
```

该提交把 Timeline 改回：

```qml
boundsBehavior: Flickable.DragAndOvershootBounds
bounceEnabled: true
```

这次改动恢复了 Timeline 的超出回弹，但重新打开了“helper 写越界值”和“ListView/Flickable 边界处理”之间发生时序冲突的可能性。

### 4.3 通用滚动助手的同向输入历史

提交 `9bcb28d4e`：

```text
fix: 防止边界回弹被同向输入反复重启
```

它曾引入边界输入门闸，核心意图是：

- 同一边界、同一方向的后续输入不重复启动 bounce。
- 反向滚轮进入内容区后解除门闸。

提交 `90add7677`：

```text
revert: 回滚滚动回弹改造
```

回滚了整套当时的确定性回弹改造，包括这类门闸逻辑。

提交 `68b93ec4b`：

```text
fix: synchronize smooth scrolling with presented frames
```

随后把 `SmoothScrollHelper` 改成通过 `SmoothScrollFrameDriver` 跟随实际呈现帧推进动画。这个版本保留了新的逐帧状态机，但没有恢复完整的同向输入门闸。

提交 `ff3abfc59`：

```text
fix: clear smooth scroll overshoot after bounce
```

进一步修正了 bounce 结束时的 overshoot 状态清理。

当前本地 PrismQML `main` 的相关基线包含这些后续逐帧改动，但不包含我后续尝试添加的门闸或 Timeline 禁用回弹改动。

## 5. 真实复现与验证证据

### 5.1 通用 ScrollBar 回归序列

在 PrismQML 本地测试夹具中，恢复了历史上对应的连续同向输入场景：

1. 将滚动区域置于底部。
2. 发送第一次向上滚轮。
3. 在回弹期间继续发送 5 次同向向上滚轮。
4. 观察 `contentY` 峰值。

当前未加门闸时，真实测试失败：

```text
first_peak = 348
后续连续同向输入后的 max(values) = 436
```

这证明“同向 wheel 反复重新触发 bounce”确实存在。

### 5.2 Timeline 虚拟列表观察

在 Timeline 虚拟列表夹具中观察到：

- 虚拟行回收会动态改变 `originY`、`contentHeight`，进而改变 `minScroll/maxScroll`。
- 某些采样中旧的 `contentY` 会短暂高于新的 `maxScroll`，例如：

```text
contentY = 5294
新的 maxScroll = 5171
```

- 这不是允许用户看到的“正常 overshoot”本身，而是动态重测后旧滚动状态没有立即和新边界收敛。
- 如果连续 wheel 输入同时重新触发 bounce 或重新启动目标动画，就会形成上下反复拉扯。

### 5.3 重要限制

已有的 PrismQML Timeline 测试主要覆盖：

- 单次两端 wheel overshoot。
- 动态 origin 的程序化滚动。
- 虚拟行追加和滚动条状态。

需要 Claude 补充的真正回归测试必须覆盖：

- 虚拟 Timeline，而不是只有普通 Flickable/ScrollArea。
- 连续同方向 wheel 输入。
- 输入发生在 outward bounce 阶段以及 bounce return 阶段。
- 委托回收导致 `originY/contentHeight` 变化的同时继续 wheel。
- 仍然允许第一次超出滚动，并且仍然回到边界。
- 不允许同向输入把 bounce 峰值一次次放大或令 `contentY` 反向跳动。

## 6. 我做过但已按用户要求回滚的内容

用户要求回滚的边界是：从用户明确说“不是那个回弹……”之后，我尝试的所有引擎修改全部撤销；只保留更早已经存在的引擎工作区内容。

### 6.1 已回滚的第一次尝试

提交：

```text
5e38a717a 修复同向滚轮重复触发边界回弹
```

修改文件：

- `prismqml/PrismQML/controls/containers/ScrollBar/SmoothScrollHelper.qml`
- `tests/qml/test_scroll_bar_conventions.py`

修改内容：

- 增加 `_blockedBounceBoundaryV/H`。
- 同一边界同一方向的后续 wheel 直接 return。
- 进入正常内容区时清除门闸。
- 增加通用 ScrollBar 连续同向滚轮回归测试。

该提交随后由：

```text
6ea7c1c87 Revert "修复同向滚轮重复触发边界回弹"
```

精确回滚。当前不应再把 `5e38a717a` 的代码当作已存在修复。

### 6.2 已回滚的第二次尝试

在 Timeline 组件上临时改过：

```qml
boundsBehavior: Flickable.StopAtBounds
bounceEnabled: false
```

文件：

```text
prismqml/PrismQML/controls/containers/TimelineCore.qml
```

这确实消除了 Timeline 的 overshoot 抖动，但同时关闭了用户明确要求保留的“超出滚动”，因此已回滚，不能作为最终修复。

### 6.3 已回滚的第三次尝试

把：

```qml
interval: Enums.duration.instant
```

临时改成：

```qml
interval: 0
```

文件：

```text
prismqml/PrismQML/controls/containers/ScrollBar/_internal/SmoothScrollBoundsReconcileTimer.qml
```

意图是让动态边界重测立即校正，但这是共享滚动器时序的扩大修改，且没有证明它是正确的 Timeline 专用解决方案，已回滚。

### 6.4 已回滚的临时测试改动

`tests/qml/test_timeline_conventions.py` 中我曾：

- 把原来的单次 bounce 测试改成 StopAtBounds 语义。
- 增加连续同向 wheel 测试。
- 增加动态边界采样断言。
- 临时加入过诊断打印。

这些测试改动已经全部恢复，不要把它们视为当前正式测试基线。

## 7. 当前必须保持的状态

### 必须保留

- Gitora 开发态优先使用本地 `D:\PrismQML\PrismQML`。
- Gitora `app_qml/requirements.txt` 仍精确锁定正式版本 `prismqml==0.4.1.5`，不要把本地源码版本写成新的伪正式版本。
- 用户已有的 Gitora 和 PrismQML 工作区改动必须保留。
- Timeline 仍然需要支持超出滚动。

### 不要做

- 不要简单把 Timeline 的 `bounceEnabled` 永久改成 `false` 作为最终修复。
- 不要把 `StopAtBounds` 当成满足用户需求的最终方案。
- 不要只修 Mica 或 Updater 日志。
- 不要只修 `historyTimeline` 作用域警告就声称滚动回归已修复。
- 不要把普通 ScrollArea 的回归通过当成 Gitora 历史 Timeline 已修复。
- 不要恢复或覆盖我已经回滚的 `5e38a717a` 内容。
- 不要回滚 PrismQML 工作区中与本问题无关的 `NavigationWindowCore`、`python/runtime/*`、`examples/main.py`、logger 或其他用户改动。

## 8. 推荐 Claude 的修复方向

先写一个真正失败的 Timeline 回归测试，然后修复实现。测试必须同时证明：

1. 第一次连续同向 wheel 到边界时仍能超出并执行一次 bounce。
2. outward/return 阶段的同向 wheel 不会重复重启同一边界的 bounce。
3. 动态 `originY/contentHeight` 重测时，滚动状态及时收敛到新的合法边界。
4. 反向 wheel 进入内容区后，下一次到边界仍可再次触发 bounce。
5. `contentY` 在连续同向输入序列中不出现与输入方向相反的明显跳变。
6. 普通 ScrollArea、横向滚动、滚动条拖拽和 Timeline 原有测试不回归。

实现选择可以在 `SmoothScrollHelper` 或 Timeline 专用包装层完成，但必须解释所有权边界：

- 如果修通用 helper，需证明普通列表也需要同样语义，并覆盖普通/横向场景。
- 如果只修 Timeline，需把 Timeline 的动态边界和连续 wheel 状态隔离在 Timeline 所有权内。
- 可以保留 bounce，但需要让同边界同方向输入合并/锁定，而不是把 bounce 关闭。
- 动态边界变化时应优先校正目标、当前动画帧和合法边界之间的关系，避免旧 `_targetY/_smoothY` 与新 `_minY/_maxY` 互相反写。

## 9. 开始工作前的检查命令

在 `D:\PrismQML\PrismQML`：

```powershell
git status --short --branch
git diff -- prismqml/PrismQML/controls/containers/TimelineCore.qml
git diff -- prismqml/PrismQML/controls/containers/ScrollBar/SmoothScrollHelper.qml
git diff -- prismqml/PrismQML/controls/containers/ScrollBar/_internal/SmoothScrollBoundsReconcileTimer.qml
git log --oneline --all -- prismqml/PrismQML/controls/containers/TimelineCore.qml
git log --oneline --all -- prismqml/PrismQML/controls/containers/ScrollBar/SmoothScrollHelper.qml
```

预期：上面三个相关源码文件不应包含我在本次交接前临时修改的 diff；其他工作区改动可能存在，必须保留。

在 `D:\PrismQML\Gitora`：

```powershell
Remove-Item Env:PRISMQML_ROOT -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -c "import app_qml.main_qml as m, prismqml; print(m.PRISMQML_PKG_DIR); print(prismqml.__file__); print(prismqml.__version__)"
```

预期开发态导入路径：

```text
D:\PrismQML\PrismQML\prismqml\__init__.py
```

## 10. 验收结论标准

只有在同一个 Timeline 真实连续 wheel 输入序列上，能指出：

- 第一次 overshoot 仍存在；
- 同方向持续输入不再产生上下反复抖动；
- 反向输入后 bounce 能重新触发；
- 动态虚拟行回收期间没有旧边界/新边界互相拉扯；

才能说这个问题修好了。仅源码看起来合理、仅普通 ScrollBar 测试通过、或仅日志警告消失，都不够。

---

## 11. 本轮（2026-08-28）执行结果

提交：PrismQML `b0374a93f` "fix: 滚轮撞边界期间的重复回弹与滚动抖动判据"。

### 11.1 已修复并验证

新增 `_internal/SmoothScrollOvershootGuard.qml` 承担超出仲裁，`_internal/SmoothScrollBoundsReconciler.qml`
接管边界重对齐（后者是为让 helper 保持在 500 行门禁内）。行为契约：

- 视图把超出夹回界内 ⇒ 撤销该边界在**本输入串**内的外移；后续同向 tick 只把目标钉在边界，不再开外移腿。
- 空闲 ≥ `Enums.scroll.input_burst_gap`（120ms）⇒ 重新武装，反向输入与新一串滚轮的回弹不受影响。
- 整段外移窗口无帧后的补算峰值同样由门闸弃帧（原先是 helper 内联的 `_discardStaleOutwardFrame*`）。

验收对应第 10 节：首次 overshoot 保留、反向输入可重新回弹、虚拟行回收期间不再有两条校正路径互拉，
均由 `tests/qml/test_timeline_conventions.py` 与 `test_scroll_bar_conventions.py` 覆盖并通过。

### 11.2 判据修正（重要，避免下轮重蹈）

原回归判据用**越界距离** `minimum - contentY` 判单调，这把边界移动引入了度量：delegate 重新测量
让 `minScroll` 内移几像素，该距离就下降并击穿容差，而 `contentY` 从未被拉回 —— 纯假阳。
现改为在**原始 `contentY`** 上检测外移期间的反向跨越（"拽回"），对边界移动免疫。

三种度量在同一场景下的实测（修复前代码）：

| 度量 | 修复前 | 能否判别 |
|---|---|---|
| 边界穿越次数 | 3（= 修复后的 3） | 否 |
| 越界期间方向反转数 | **0** | 否 |
| 原始 contentY 拽回 | 3 处 | **是** |

反转数抓不到的原因：缺陷形态是"夹回边界 → 继续外移"，夹紧帧恰好落在 `contentY == minScroll`，
任何"仅统计越界样本"的过滤器都会跳过它。修复前的失败数据：
`yanks=[(6,-14.0,0.0), (14,-17.0,-0.0), (39,-70.0,-0.0)]`，`minScroll` 全程 `0.0`。
该判据在修复前代码上 3/3 失败，可作可信门禁。

### 11.3 未修复的残留（下一轮的起点）

`test_timeline_virtual_continuous_same_direction_wheel_keeps_one_bounce` 仍有约 **1/20** 概率失败，
已按用户决定标 `xfail(strict=False)`，缺陷保持可见但套件确定。三次实测：3/60、2/60、4/60
（分别对应修复后、加返回腿钩子后、重建后），n=60 下互为噪声。

形态高度一致，真实样本存于 PrismQML `.artifacts/scroll-diag/residual*/`：

| 样本 | 拽回 1 | 拽回 2 |
|---|---|---|
| fail_23 | 下标 16，-35.0 → -0.0 | 下标 33，-70.0 → -0.0 |
| fail_39 | 下标 15，-34.0 → -0.0 | 下标 33，-71.0 → -0.0 |
| fail_50 | 下标 14，-33.0 → -0.0 | 下标 31，-69.0 → -0.0 |

`minScroll` 全程静止在 `0.0`，落点恰是边界，随后继续外移到约 -70。

已排除/已知：

- **不是**判据假阳。新判据对边界移动免疫，且边界在该场景确实没动。
- **不是**视图夹紧。`isRevoked(-0.0, -34.0, …)` 会返回真，若是夹紧则下一帧就被截断。
- **不是**返回腿走完后重开外移腿。我曾据此加 `noteReturnSettled()`（在 `_onFrameDriverSettled`
  的返回腿到达分支武装撤销），失败率 3/60 → 2/60 无实质变化，且无法观测到它触发，已按纪律回退，
  未进入提交。该假设仍未被证伪，只是缺证据。
- **-36 → -0.0 是单帧跳变**，前后无中间样本。返回腿是 250ms 动画、采样 pump 40ms，本应有中间值；
  没有 ⇒ 这个 `0` 是被**直接写入**的，不是动画走到的。下一轮应从"谁直接写了 contentY/`_smoothY`"入手，
  候选：`_syncing` 期间的 `moveTo`、`setImmediate`、`boundsReconciler.reconcile` 的空闲轴接管分支。

### 11.4 观测方法上的坑

加探针会让它不复现：在 `contentYChanged` 回调里多读三个属性即从 30 次 0 命中（基线约 1.5 次）。
下一轮若要观测，**不要**在采样回调里读属性，改为门闸内部累加计数器、测试结束后一次性读取；
或直接在 QML 侧记录写入者标记，避免任何跨语言属性读取进入热路径。

### 11.5 复现命令

```bash
for i in $(seq 1 60); do ./.venv/Scripts/python.exe scripts/test_process.py --qt-platform offscreen --timeout 300 -- ./.venv/Scripts/python.exe -m pytest -q -rx tests/qml/test_timeline_conventions.py -k continuous_same_direction -p no:cacheprovider 2>&1 | grep -oE "[0-9]+ (passed|failed|xfailed|xpassed)" | tr '\n' ' '; echo " <- run $i"; done
```
