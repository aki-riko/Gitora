# Gitora 开发与发版规范

> 本文档是 Gitora 的开发/发版铁律。贡献代码(含 AI 协作)前必须通读。
> Gitora 是基于 [PrismQML](https://github.com/aki-riko/PrismQML) 引擎的 Git 可视化 GUI。

## 一、技术栈与结构

- **前端**:纯 QML(QtQuick / PySide6),UI 组件来自 PrismQML 引擎
- **后端**:Python 3.12,`app_qml/` 为 QML 版入口,`app/` 为公共设施(setting/logger 等)
- **引擎依赖**:`prismqml`(PyPI 分发),约束见 [app_qml/requirements.txt](app_qml/requirements.txt)
- **打包**:Windows 用 Nuitka standalone + Inno Setup;macOS 用 GitHub Actions + Nuitka

## 二、Git 与远程

本仓库有两个远程,推送时**两个都要推**:

- `origin` = Gitea(`ssh://git@git.9li.life:28022/Aquila/Gitora.git`)
- `github` = GitHub(`git@github.com:aki-riko/Gitora.git`)—— **CI / Release 在这**

以 `git remote -v` 实测为准。GitHub Release 页面挂发行产物(Windows .exe + macOS .dmg),用户从这里下载。

## 三、版本号规范

语义化版本 `vX.Y.Z`。bugfix 升 Z,功能升 Y。**版本号必须同步三处,并用同一版本重新生成安装器脚本**:

1. [app/common/setting.py](app/common/setting.py) 的 `VERSION = "vX.Y.Z"`(带 v 前缀)
2. [build_nuitka.py](build_nuitka.py) 的 `--product-version=X.Y.Z`(不带 v)
3. [build_nuitka_mac.py](build_nuitka_mac.py) 的 `--product-version=X.Y.Z`(不带 v)
4. `prismqml-installer.json` 只保存稳定应用身份,不保存版本;用 `X.Y.Z` 生成 [installer.iss](installer.iss),禁止手改生成文件

## 四、升级 PrismQML 引擎依赖

当修复/特性依赖引擎新版时:

1. 引擎侧先发版到 PyPI(见 PrismQML 仓库 AGENTS.md 的发版规范)
2. Gitora venv 升级:`.venv/Scripts/python.exe -m pip install -U "prismqml==X.Y.Z.N"`
3. 确认:`.venv/Scripts/python.exe -c "import prismqml; print(prismqml.__version__)"`
4. `app_qml/requirements.txt` 必须精确锁定同一正式版,不可只写宽泛下限

## 五、Windows 打包

1. 确保 venv 已装最新 `prismqml` 与依赖
2. `.venv/Scripts/python.exe build_nuitka.py`
   - Nuitka standalone/onedir,产物在 `build_dist/main_qml.dist/Gitora.exe`
   - 验证产物能启动(打安装包前先自检):在 `build_dist/main_qml.dist/` 下
     `GITESS_QML_SELFTEST=1 ./Gitora.exe`,看到 `exit=0` + `[SELFTEST] QML 加载成功,rootObjects = 1` 即通过
3. 先生成并检查脚本(以下 `X.Y.Z` 与 `VERSION` 去掉 `v` 后一致):
   `.venv/Scripts/python.exe -m prismqml.python.tools.windows_installer generate --manifest prismqml-installer.json --version X.Y.Z --output installer.iss`
   `.venv/Scripts/python.exe -m prismqml.python.tools.windows_installer check --manifest prismqml-installer.json --version X.Y.Z --output installer.iss`
4. 出安装包:
   `.venv/Scripts/python.exe -m prismqml.python.tools.windows_installer compile --manifest prismqml-installer.json --version X.Y.Z --output installer.iss`
   - 产物在 `dist_installer/Gitora-Setup-X.Y.Z.exe`
   - ISCC 未加入 `PATH` 时,通过环境变量 `PRISMQML_ISCC` 传入实际 `ISCC.exe` 路径,禁止写死开发机路径
   - 仅 `compile` 会调用 ISCC;`doctor`、`generate`、`check`、`compile --dry-run` 均无编译副作用
   - `installer.iss` 由清单确定性生成,路径保持项目相对路径

## 六、macOS 打包(GitHub Actions)

macOS 的 .app/.dmg **不能在本地(Windows)构建**,必须触发 CI:

1. `gh workflow run build-macos.yml --ref master`(在含目标版本改动的分支上)
2. `gh run watch <run-id> --exit-status` 等构建完成(约 8 分钟)
   - CI 在 macos-14 runner 上 `pip install -r app_qml/requirements.txt`(自动拉 PyPI 上的 prismqml),Nuitka 打 .app → 重签 → 打 dmg → SELFTEST
3. 下载产物 artifact:`gh run download <run-id> -n Gitora-macOS-unsigned -D <目录>`
   - artifact 内是 `Gitora-macOS.dmg`(unsigned,ad-hoc 签名)

## 七、发布 GitHub Release(收尾,必做)

历史每个版本都在 GitHub Release 挂 **Windows .exe + macOS .dmg**。发版收尾:

1. 打 tag 并推**两个**远程:
   ```bash
   git tag vX.Y.Z
   git push github vX.Y.Z
   git push origin vX.Y.Z
   ```
2. 建 release 并上传两个产物:
   ```bash
   gh release create vX.Y.Z \
     dist_installer/Gitora-Setup-X.Y.Z.exe \
     <mac下载目录>/Gitora-macOS.dmg \
     --title "Gitora vX.Y.Z" --notes "<变更说明>"
   ```

## 八、发版检查清单

- [ ] 三处版本号已同步,并用同一版本生成且 `check` 通过
- [ ] 引擎依赖已升级并确认版本
- [ ] `git push` main/master 到 github + origin **两个**远程
- [ ] Windows 安装包已出并本地验证能启动
- [ ] mac CI 已触发且成功,dmg 已下载
- [ ] tag 已推两个远程
- [ ] GitHub Release 已建,exe + dmg 均已上传

## 九、省时技巧

mac CI 与 Windows 打包互不依赖,可并行:先 `gh workflow run build-macos.yml --ref master` 把 CI 跑起来(约 8 分钟),同时本地跑 Nuitka + ISCC。两条线并行,总耗时约等于 mac CI 单程。等 CI 时用 `gh run watch <id> --exit-status` 阻塞等待,省去反复轮询。

## 十、历史时间线连续滚轮回弹排查

历史页使用虚拟化 `Timeline` 时,出现“滚轮仍未松开却被拉回,随后又继续向外滚”的现象,先按以下已确认机制排查,不要直接归因于刷新:

- 虚拟 `ListView`/`Flickable` 会在边界处夹紧 `contentY`,而 `SmoothScrollHelper` 同时可能写入越界位置执行回弹;两条路径竞争时会出现 `contentY -> originY(通常为 0) -> 再次越界` 的单帧跳变,表现为闪回或上下抖动。
- 虚拟委托回收和重建会动态改变 `originY`、`contentHeight`、`maxScroll`;旧的 `contentY`、动画目标和新边界短暂不一致,会放大上述竞争。持续同方向 wheel 还可能重复启动同一边界的外移/回弹。
- 业务层刷新不是默认解释。只有同时看到 `historyChanged`、`log.request`/`logReady`、`allCommits.changed` 或 `timelineItems.changed` 等刷新链路事件,才能把某次跳变归因于刷新;这些事件缺失而只有 `contentY`/边界/滚动助手状态变化时,应按滚动仲裁问题处理。
- 分页追加与刷新替换不能共用同一个滚动静默门槛:接近预取线时应立即发下一页请求,`logReady` 返回的 `skip > 0` 页面直接追加;只有会替换首段数据的 `skip = 0` 刷新结果才等待滚动静默后应用。否则会把防止刷新闪回的等待错误地施加到分页,造成每页额外等待约 750ms,看起来像动态加载失效。
- 禁止在业务层 `contentYChanged` 或滚轮回调中反复强写 `contentY`“纠正”位置;`ListView` 会再次夹紧,容易形成递归抖动。也不要仅为消除抖动而永久关闭 Timeline 的 overshoot/bounce,除非需求明确允许改变原有交互。
- 观测使用环境变量 `GITORA_TIMELINE_TRACE=1`,日志写入 `%LOCALAPPDATA%\\Gitora\\logs\\`;观测代码默认关闭。排查结束后执行 `Remove-Item Env:GITORA_TIMELINE_TRACE -ErrorAction SilentlyContinue` (或设为 `0`),完全退出并重启应用,避免把 DEBUG 观测状态当成修复条件。

该问题的验收必须使用真实的虚拟 Timeline 连续同向 wheel 序列:首次越界能力仍保留,滚轮未松开期间不出现边界往返或反向明显跳变,动态委托重测不再让旧边界与新边界互相拉扯,反向输入后仍可重新触发正常回弹。修复应归属于统一的滚动/视觉位移仲裁层,不能把刷新回填逻辑当作滚动状态机。

## 十一、主线程停顿观测(长跑变慢类问题的第一手证据)

“长时间运行后点击/下拉响应变慢甚至卡住”属于**主线程被占住**或**渲染/原生资源累积**两类问题之一。没有真实停顿数据时禁止直接归因于引擎弹层或业务刷新,先上观测:

- 观测开关 `GITORA_STALL_TRACE=1`;打点间隔 `GITORA_STALL_TRACE_INTERVAL_MS`(默认 100),停顿阈值 `GITORA_STALL_TRACE_THRESHOLD_MS`(默认 250,且被强制 >= 间隔×2)。
- 每条记录形如 `[STALL_TRACE] #N t=<ms> gap=<实际间隔>ms interval=.. threshold=.. busy=<Git 操作中?> windows=<进程顶层窗口数>`,写入 `%LOCALAPPDATA%\Gitora\logs\gitess_YYYYMMDD.log`。
- 判读方式:`gap` 变大且 `busy=true` / 与刷新链路事件同时出现 → 业务主线程被占住;`gap` 变大但 `busy=false` 且 `windows` 持续增长 → 原生窗口/渲染资源累积,按引擎侧处理;`gap` 正常而弹层仍慢 → 问题在弹层的显示路径而不是主线程调度。
- QML 的 `console` 输出**不会**落进 Gitora 日志文件,观测必须经 `QmlRenderBridge.logStallTrace` 写日志(`StallTraceProbe` 已如此实现)。
- 观测默认关闭,启用后必须完整重启应用;排查结束执行 `Remove-Item Env:GITORA_STALL_TRACE -ErrorAction SilentlyContinue`(或设为 `0`)并再次完整重启,禁止把观测状态当成修复条件。

## 十二、崩溃取证观测与全内存转储

Gitora 的历史崩溃多为 Qt 侧**原生访问违例**(`0xC0000005`),进程被直接终止:Python 层没有 traceback,业务日志止于崩溃前最后一条(例如 2026-09-14 02:52 那次,`Qt6Qml.dll+0x1a3790`,`movzx eax, byte ptr [rbx]`,`rbx=0x2B23B099000` 未映射)。这类问题**禁止**在没有真实现场时直接改代码:

- 观测开关 `GITORA_CRASH_TRACE=1`(默认关闭,关闭时不注册任何处理器、不改任何环境变量):
  - `faulthandler` 捕获 Windows 致命异常,把崩溃时刻**所有线程的 Python 栈**写入 `%LOCALAPPDATA%\Gitora\logs\gitora_crash_YYYYMMDD.log`(首行形如 `Windows fatal exception: access violation`)。这是原生崩溃唯一能留下的 Python 现场。
  - Qt 消息处理器把 Qt/QML 的 warning/critical/fatal(含 `file:line`)以 `[QT] <file>:<line> <msg>` 写入 Gitora 日志,同时保留 Qt 默认的 stderr 输出。
  - QML 引擎 `engine.warnings` 逐条以 `[QML] ...` 落日志。
- `GITORA_QML_TRACE=1` 额外打开 `QML_IMPORT_TRACE`、`QSG_INFO` 与 `qt.qml.binding.removal.info`,用于定位具体 QML 文档与绑定销毁。
- QML 侧面包屑经 `QmlRenderBridge.logCrashTrace`(`GitoraCrashTraceEnabled` 门控),QML 的 `console` 输出不落日志文件,必须走这个通道。
- 全内存转储:`HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\{python.exe,Gitora.exe}` 设 `DumpType=2`(REG_DWORD,全内存)、`DumpCount=10`、`DumpFolder=%LOCALAPPDATA%\Gitora\CrashDumps`(REG_EXPAND_SZ)。**该键在 HKLM,配置需要管理员**;不设 `DumpType` 时 WER 默认只写 mini 转储(堆数据缺失,无法定位 QML 文档)。
- 复验限制:在 DSH/沙箱会话内派生的进程位于 Job 对象中(受限令牌),其崩溃**不会**进入 WER,因此转储只能由用户自己启动的实例产生;会话内只能验证配置值本身,不能验证落盘结果。
- 判读:拿到转储后用 `%TEMP%` 下的零依赖解析脚本读异常流、模块表、寄存器与栈回溯;`.pdata`(RUNTIME_FUNCTION)可在无符号条件下精确界定崩溃函数边界。
- 观测默认关闭,排查结束执行 `Remove-Item Env:GITORA_CRASH_TRACE,Env:GITORA_QML_TRACE -ErrorAction SilentlyContinue` 并完整重启,禁止把观测状态当成修复条件。
