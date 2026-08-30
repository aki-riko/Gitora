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
- 禁止在业务层 `contentYChanged` 或滚轮回调中反复强写 `contentY`“纠正”位置;`ListView` 会再次夹紧,容易形成递归抖动。也不要仅为消除抖动而永久关闭 Timeline 的 overshoot/bounce,除非需求明确允许改变原有交互。
- 观测使用环境变量 `GITORA_TIMELINE_TRACE=1`,日志写入 `%LOCALAPPDATA%\\Gitora\\logs\\`;观测代码默认关闭。排查结束后执行 `Remove-Item Env:GITORA_TIMELINE_TRACE -ErrorAction SilentlyContinue` (或设为 `0`),完全退出并重启应用,避免把 DEBUG 观测状态当成修复条件。

该问题的验收必须使用真实的虚拟 Timeline 连续同向 wheel 序列:首次越界能力仍保留,滚轮未松开期间不出现边界往返或反向明显跳变,动态委托重测不再让旧边界与新边界互相拉扯,反向输入后仍可重新触发正常回弹。修复应归属于统一的滚动/视觉位移仲裁层,不能把刷新回填逻辑当作滚动状态机。
