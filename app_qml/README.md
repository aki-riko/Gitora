# Gitora — 架构说明

基于 [FluentQML](https://github.com/)(MIT,纯 QML 声明式 Fluent 组件库)构建的 Git GUI。本文件说明项目架构与设计,面向贡献者。

## 架构分层

- **界面层**(`app_qml/qml/`):纯 QML 声明式,`views/` 是各功能页面,`components/` 是可复用对话框/组件。
- **对接层**(`app_qml/backend/`):`git_bridge.py` 把后端 `GitService` 包装成 QML 友好接口(dataclass→dict、`@Slot` 暴露、信号驱动异步);`repo_scanner.py` 后台全盘扫描仓库。
- **后端层**(`app/common/`):`git_service.py` 封装全部 git 命令(subprocess + 输出解析),与 UI 解耦,可独立测试。
- **入口**(`app_qml/main_qml.py`):创建 FluentQML App、注册后端到 QML 上下文、加载 `main.qml`。

> 项目由早期的 QWidget + QFluentWidgets Pro 版本迁移而来,后端 `git_service.py` 是迁移中保留复用的核心资产。

## 运行

```bash
# 1. 安装依赖(含 FluentQML: pip 包名 fqml >= 0.2.5)
pip install -r app_qml/requirements.txt

# 2. 启动
python app_qml/main_qml.py
```

> 开发时若要用本地 FluentQML 源码而非 pip 包,设环境变量 `FLUENTQML_ROOT` 指向源码目录(入口会优先 import 已装的 pip 包,本地源码仅作回退)。

## 目录结构

```
app_qml/
├── main_qml.py              # 入口(单实例检查 + Git 检测 + 注册后端 + 加载 QML)
├── requirements.txt
├── backend/
│   └── git_bridge.py        # GitService 的 QML 对接壳(dataclass→dict, @Slot 暴露)
└── qml/
    ├── main.qml             # 主窗口(导航壳 + 页面路由)
    ├── views/               # 各功能页面
    │   ├── RepoView.qml         # 仓库:变更列表/暂存/提交/diff/推送
    │   ├── HistoryView.qml      # 历史:提交列表/搜索/详情/reset/cherry-pick
    │   ├── BranchView.qml       # 分支:本地+远程/切换/创建/删除
    │   ├── TagView.qml          # 标签
    │   ├── StashView.qml        # 暂存(stash)
    │   ├── ConflictView.qml     # 冲突解决
    │   └── SettingsView.qml     # 设置
    └── components/          # 可复用对话框/组件
        ├── GuideShell.qml       # 分步引导外壳(Stepper + StackedWidget)
        ├── InitRepoGuide.qml    # 初始化仓库引导
        ├── DangerDialog.qml     # 危险操作倒计时确认
        ├── CloneDialog.qml / CleanDialog.qml / RemoteDialog.qml
        └── CommitDetailDialog.qml / ReflogDialog.qml
```

## 设计原则

- **后端只重构对接层**:GitService 的 Git 命令/subprocess/输出解析逻辑保留,GitBridge 只做数据格式转换(dataclass→dict)和异步信号转发。
- **同步操作**直接返回 `[ok, msg]`;**异步操作**(push/pull/clone/gc/merge/quickCommitPush)经 `operationStarted/operationFinished` 信号回传。

## 验证状态

- QML 组件加载、后端数据流(getStatus/getLog/分页/搜索/branch/tag/reflog/diff 等)已用真实 git 仓库验证。
- GuideShell 翻页已端到端验证。
- **交互行为**(点击/拖拽/对话框确认/主题切换)需真机运行验证。

## 未迁移项

- `FileHistoryDialog`(文件版本对比)、`ConflictViewerDialog`(冲突内容查看)— 低频,后续补。
- `virtual_file_list` — 被 QML ListView 原生虚拟滚动取代。
