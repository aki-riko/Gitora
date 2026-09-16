# 启动卡死根因:GUI 主线程枚举盘符时探测网络盘

> 记录日期:2026-09-16
> 现象:应用启动后停在启动页(揭幕阶段)再也不进入主界面,Windows 记录 `AppHangB1`。
> 结论:与仓库页工具栏改动无关;根因是 `RepoScanner.start()` 在 **GUI 主线程**上
> 用 `os.path.isdir` 逐个探测盘符,其中映射到网络共享的盘符(本机 `Z:`)在远端无
> 响应时会阻塞数十秒,主线程因此不再回到事件循环。

## 一、现场证据(真实日志,非推断)

`%LOCALAPPDATA%\Gitora\logs\gitess_20260916.log` 中两次卡死启动(14:28:42、14:29:02)
的最后一行都停在引擎的揭幕起点:

```
[2026-09-16 14:28:43] [INFO] [PrismQML:317] FastSplash 主窗口就绪: frames=9, splash_frames=71
[2026-09-16 14:28:43] [INFO] [PrismQML:317] FastSplash 开始圆环揭幕: 500ms / easing=14
（此后无任何日志;下一次日志是 14:29:02 的另一次启动）
```

对照同一份代码的正常启动(14:35:22,IPC 陈旧锁接管后成功):

```
[2026-09-16 14:35:23] [INFO] [RepoScanner:115] 开始扫描 Git 仓库,根目录: ['B:\\', 'C:\\', 'D:\\', 'K:\\', 'L:\\', 'Z:\\']
[2026-09-16 14:35:24] [INFO] [PrismQML:317] FastSplash 揭幕完成, 交接主窗口
```

- 关键差异:**卡死的那两次没有任何 `开始扫描 Git 仓库` 行**。
- 系统事件日志:`[2026-09-16 14:29:01] Event 1001 AppHangB1,python.exe`(主线程无响应),
  与「启动页停在揭幕阶段、主线程不再处理消息」一致。
- 主线程被占住的旁证:启动后 1.5s 的扫描定时器与揭幕交接的 250ms 兜底定时器**都没有
  触发**(两者都在主线程上,消息循环被同步调用卡住时无法执行)。

## 二、代码路径

`app_qml/main_qml.py`:

```python
_QTimer.singleShot(1500, repo_scanner.start)   # 主线程
```

`app_qml/backend/repo_scanner.py`(修复前):

```python
def start(self, roots=None):
    roots = list(roots) if roots else _list_fixed_drives()   # ← 主线程做磁盘探测
    logger.info(f"开始扫描 Git 仓库,根目录: {roots}")          # ← 探测成功后才落日志
    ...

def _list_fixed_drives():
    for letter in string.ascii_uppercase:
        if os.path.isdir(f"{letter}:\\"):                    # ← 对 Z: 会等网络超时
            drives.append(root)
```

日志行位于枚举**之后**,因此枚举阻塞时日志自然缺失 —— 与第一节的现场完全吻合。
本机盘符实测:`Z:` 为 `DriveType=4`(网络),`net use` 无对应映射(断开的远端),
其余 `B:/C:/D:/K:/L:` 为本地固定盘(`DriveType=3`)。

仓库自身的约定也印证这是已知风险类别 —— `app/common/opened_repos.py`:

> 会对每个路径做一次 `exists()`;调用方必须放后台线程。

同一类「网络路径探测」在扫描器里却落在了主线程上。

## 三、修复

1. `repo_scanner.py`:盘符枚举与日志移入线程池任务(`_resolve_scan_roots`),`start()`
   在主线程只做状态切换与任务提交,毫秒级返回;显式传入 `roots` 的语义不变。
2. `scanned_repos.py`(同类加固):缓存存在性校验对**远端路径**(映射网盘 / UNC)
   跳过探测(`GetDriveTypeW` 只读本地挂载表,不访问网络),避免同一条主线程在启动
   阶段对远端路径 `exists()` 阻塞;条目保留,打开失败时由业务反馈。

## 四、验证

- 回归测试 `tests/test_prism_task_migration.py::test_repo_scanner_resolves_drive_roots_off_the_calling_thread`:
  用「阻塞 0.4s 的假枚举」模拟无响应网盘,断言 `start()` 在调用线程内 <0.2s 返回、
  枚举发生在非主线程,且扫描仍能完成。
  **修复前该测试失败**:`assert 0.39100000000325963 < 0.2`(start() 在调用线程阻塞
  391ms 并同步打印了扫描日志),修复后通过。
- 真实启动(修复后):`开始扫描` 与 `FastSplash 揭幕完成` 均正常出现。
- 定向测试:`tests/test_prism_task_migration.py`、`tests/test_scanned_repos_cache.py`、
  `tests/test_unbounded_io_contract.py` 等相关文件全部通过。

## 五、残留风险(本次未改动,记录备查)

1. `ScannedReposCache` 仍会在启动路径(主线程)对**本地**缓存路径做 `exists()`
   (本机约 140 条,实测 ~0.1s)。远端路径已跳过;若缓存规模继续增长,应把校验整体
   挪到线程池。
2. 引擎侧 `prismqml/python/core/shadow.py` 的 `DwmSyncFilter.nativeEventFilter` 在
   交互式移动/缩放消息(`WM_SIZING`/`WM_MOVING`,以及缩放循环内的 `WM_SIZE`)里
   **同步调用 `DwmFlush()`**。该调用等待合成器完成,理论上可长时间阻塞主线程;
   本仓库不改引擎,若以后出现「拖动/缩放窗口时卡死」,应优先查这条路径并考虑加超时。
