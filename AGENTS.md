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

- `origin` = Gitea(`git@git.9li.life:Aquila/Gitora.git`)
- `github` = GitHub(`git@github.com:aki-riko/Gitora.git`)—— **CI / Release 在这**

以 `git remote -v` 实测为准。GitHub Release 页面挂发行产物(Windows .exe + macOS .dmg),用户从这里下载。

## 三、版本号规范

语义化版本 `vX.Y.Z`。bugfix 升 Z,功能升 Y。**版本号必须同步三处**(改一处漏两处会导致产物版本不一致):

1. [app/common/setting.py](app/common/setting.py) 的 `VERSION = "vX.Y.Z"`(带 v 前缀)
2. [build_nuitka.py](build_nuitka.py) 的 `--product-version=X.Y.Z`(不带 v)
3. [installer.iss](installer.iss) 的 `#define MyAppVersion "X.Y.Z"`(不带 v)

## 四、升级 PrismQML 引擎依赖

当修复/特性依赖引擎新版时:

1. 引擎侧先发版到 PyPI(见 PrismQML 仓库 AGENTS.md 的发版规范)
2. Gitora venv 升级:`.venv/Scripts/python.exe -m pip install -U "prismqml==X.Y.Z.N"`
3. 确认:`.venv/Scripts/python.exe -c "import prismqml; print(prismqml.__version__)"`
4. `app_qml/requirements.txt` 的约束(`prismqml>=X.Y.Z`)若已覆盖新版则无需改

## 五、Windows 打包

1. 确保 venv 已装最新 `prismqml` 与依赖
2. `.venv/Scripts/python.exe build_nuitka.py`
   - Nuitka standalone/onedir,产物在 `build_dist/main_qml.dist/Gitora.exe`
3. 出安装包:`"C:\Program Files\Inno Setup 7\ISCC.exe" installer.iss`
   - 产物在 `dist_installer/Gitora-Setup-X.Y.Z.exe`
   - `installer.iss` 的 `MyDistDir` 是相对路径,ISCC 须在仓库根目录运行

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

- [ ] 版本号三处已同步(setting.py / build_nuitka.py / installer.iss)
- [ ] 引擎依赖已升级并确认版本
- [ ] `git push` main/master 到 github + origin **两个**远程
- [ ] Windows 安装包已出并本地验证能启动
- [ ] mac CI 已触发且成功,dmg 已下载
- [ ] tag 已推两个远程
- [ ] GitHub Release 已建,exe + dmg 均已上传
