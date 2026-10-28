# 排查笔记：四类"看起来通过、实际没验证"的坑

> 记录日期：2026-10-28
> 来源：v1.10.0 / v1.10.1 两次发版期间的连续定位
> 定位：这不是某一类 bug 的根因复盘，而是**验证方法本身**的复盘。
> 四件事都属于同一模式：证据看起来齐全，但量错了对象或误读了结论。

---

## 一、pytest 版本漂移：本地全绿，CI 门禁失败

### 现象

改完代码本地跑全量通过，推 tag 后 `release.yml` 的 `quality_gate` 失败：

```
TypeError: pytest.approx() does not support nested data structures:
    (0.25, 0.25) at index 0
```

### 根因

`pyproject.toml` 写的是 `pytest>=8.4`，**没有上限**。CI 每次都装最新版：

| 环境 | pytest | `approx([(a,b),...])` |
|---|---|---|
| 本地 | 9.1.1 | 允许（宽松） |
| CI | 9.2.0 | `TypeError`（`ApproxSequenceLike.__init__` 显式拒绝嵌套） |

同一份代码在两处行为不同，表现为"版本漂移"而非"真实回归"，极难从失败信息反推。

### 判据

- 只有**列表套元组**会失败：`approx([(0.25,0.25)])`
- 纯元组 `approx((0,0,302,38))` 和纯数值列表 `approx([1.0,1.0])` **仍然合法**
- 不要凭"看到 approx 就改"，先用三种形态各跑一次最小实验

### 处理

1. 逐分量比较（保持原容差）替代嵌套 approx
2. `pytest>=8.4,<10` 加上限，避免下次静默漂移

### 教训

**"本地通过"不能作为 CI 门禁会通过的证据。** 依赖没锁上限时，跑 tag 门禁前应先在本地装成与 CI 相同的版本复验。

---

## 二、QThread 不在 `threading.enumerate()` 里

### 现象

验证"采样线程能否停止"时，用 `threading.enumerate()` 统计线程数：

```
during: 2   →  after stop: 2   判定"没退出"
```

于是判定停止逻辑失效，来回改了三轮代码。

### 根因

`run_in_thread` 创建的是 **Qt QThread**，不是 Python `threading.Thread`：

- 它不会出现在 `threading.enumerate()`
- 中途看到的那个 `Dummy-1` 是**无关的残留线程**，被当成了采样线程

### 正确判据

用引擎任务句柄的 `finished` 信号，这是唯一可靠依据：

```python
state = {"finished": False}
handle.finished.connect(lambda: state.__setitem__("finished", True))
trace.stop_task_leak_trace()
# 轮询 processEvents 直到 state["finished"] 为 True
```

### 教训

**量错对象比不量更危险**——它会给出一个确定但错误的结论，从而把排查引向错误方向。

---

## 三、字符串匹配的源码门禁会被自己注释误伤

### 现象

给任务泄漏观测补契约测试，断言不出现手写线程：

```python
assert "threading.Thread(" not in source      # 误伤
```

结果测试失败——但代码里**并没有**手写线程，失败是因为我刚写的注释里
记录了历史实现：

```python
# 历史实现直接 ``threading.Thread(...daemon=True)``，违反生产代码不得手写
```

### 处理

改用 **AST** 判定真实调用，而不是匹配源码文本：

```python
tree = ast.parse(source)
assert _calls_named(tree, "threading", "Thread") == []
```

同样的坑还有"不可中断循环"：注释里的 `while True` 字样会让文本断言失败，
而 AST 能准确区分 `while True` 与 `while not event.wait(...)`。

### 教训

门禁要盯**语义**，不要盯**文本**。源码注释本就该记录"曾经怎么写"，用文本匹配会让"写清楚的注释"反而破坏门禁。

---

## 四、测试通过 ≠ 功能正确

### 现象

任务泄漏观测改造完成，契约测试全绿。但做**功能验证**时崩溃：

```
QThread: Destroyed while thread '' is still running
```

### 根因

是我改造时自己引入的：循环读**模块级** `_stop_event`，而 `stop()` 会把它置 `None`：

```python
_stop_event = None          # stop 里
...
while not _stop_event.wait(interval):   # loop 里 → 变成 None.wait()
```

停机瞬间抛异常，线程异常存活，退出期 Qt 报线程未结束。

改为闭包捕获**局部**事件后正常：

```python
stop_event = threading.Event()   # 局部
_stop_event = stop_event         # 仅用于外部置位
def loop():
    while not stop_event.wait(interval): ...
```

### 教训

契约测试只证明"代码形态符合约定"，不证明"运行时行为正确"。

**涉及线程/资源生命周期时，必须真实跑一次启停流程并检查退出期输出**，否则崩溃发生在进程退出、测试早已结束之后。

---

## 五、可复用的验证清单

以下四条可直接用于类似排查：

1. **依赖版本**：本地复验前，把关键依赖装到与 CI 完全一致的版本
2. **线程对象**：Qt 线程用 `QThread`/`TaskHandle.finished` 判定，不要用 `threading.enumerate()`
3. **源码门禁**：用 `ast` 判定调用与语句，不用字符串匹配
4. **生命周期**：线程/定时器/资源类改动，必须真实跑启停并检查退出期 stderr

补充一条过程经验：**先做最小实验确认失败条件，再动手改**。本次一度把"1 处真实失败"误报成"42 处需要修改"，
原因是正则统计时把"纯数值列表"（合法）也算进了嵌套结构。用三种形态各跑一次最小实验，
比扫全仓更快也更准。
