# Gitora Git 功能补全计划

> 创建日期: 2026-07-09
> 目标: 将 Gitora 的 Git GUI 操作做成系统化闭环,并保证每一步都有提交和 review。

## 1. 范围

本计划覆盖 Gitora 面向用户的 Git 操作入口,不是把全部底层 `git` 子命令原样塞进界面。判定标准是:

- 新手和日常用户高频使用的操作必须有清晰入口。
- 破坏性操作必须有倒计时二次确认和明确后果文案。
- 每个操作必须能在真实 Git 仓库场景中验证,不能只靠代码静态判断。
- 前端 QML、`GitBridge`、`GitService` 三层命名和行为要保持一致。

功能矩阵见 [docs/git-operations-matrix.md](docs/git-operations-matrix.md)。

## 2. 执行纪律

每一个实现步都按下面顺序闭环:

1. Read: 先读相关 QML、`GitBridge`、`GitService` 和已有同类实现。
2. Edit: 只改本步涉及文件,不顺手重构无关代码。
3. Test: 用临时真实仓库验证 Git 行为;改 QML 时同时跑 QML selftest。
4. Review: 对本步 diff 做 review,重点看危险操作、分支/远端边界、错误提示。
5. Commit: 每步单独提交,提交信息使用 `feat/fix/docs/test/refactor: 描述`。

禁止把多个独立 Git 操作混在一个大提交里。若某步测试失败,先分析根因,不能继续叠新改动。

## 3. 已验证现状

源码核对范围:

- `app_qml/qml/views/RepoView.qml`
- `app_qml/qml/views/BranchView.qml`
- `app_qml/qml/views/HistoryView.qml`
- `app_qml/qml/views/StashView.qml`
- `app_qml/qml/views/TagView.qml`
- `app_qml/qml/views/ConflictView.qml`
- `app_qml/qml/components/RemoteDialog.qml`
- `app_qml/qml/components/CleanDialog.qml`
- `app_qml/backend/git_bridge.py`
- `app/common/git_service.py`

当前已经有不少 Git 入口: 打开/克隆/初始化、暂存/取消暂存、提交/amend、一键提交推送、普通拉取/变基拉取/fetch、普通推送/强制推送、分支创建/切换/删除/合并、远程增删改、历史 checkout/cherry-pick/revert/reset、reflog、stash、tag、冲突解决、clean/gc。

明显缺口包括: 远程强制覆盖本地、拉取/推送远程和分支选择、分支重命名、强制删除分支 UI、设置上游、远程分支检出到本地的明确流程、rebase/cherry-pick/revert 中途状态处理、stash 高级选项、tag 类型区分、worktree/submodule/LFS/bisect 等高级功能。

## 4. 分期计划

### Step 0: 文档和计划落盘

- 产物:
  - `PLAN_GIT_OPERATIONS.md`
  - `docs/git-operations-matrix.md`
- 验证:
  - `git diff --check`
  - review 文档是否覆盖现有入口、缺口、验收门禁
- 提交:
  - `docs: 落盘Git功能补全计划`

### Step 1: 测试基座

- 目标:
  - 增加可复用的真实 Git 临时仓库测试工具。
  - 覆盖本地仓库、bare remote、上下游、ahead/behind、冲突、stash/tag 等场景。
- 产物:
  - 测试 helper
  - `GitService` 核心操作回归测试
- 验证:
  - 全量新增测试通过
  - 不依赖网络和用户全局 Git 配置
- Review 重点:
  - 测试是否使用真实 Git 命令和真实仓库数据
  - 是否隔离全局配置和工作树

### Step 2: 同步类操作补全

- 目标:
  - 补齐“远程强制覆盖本地”: `fetch` 后将当前分支 `reset --hard` 到已验证上游。
  - 为拉取/推送提供远程与分支选择能力。
  - 无上游、分离 HEAD、无远程、工作区脏、远端不存在时给明确提示。
- 产物:
  - `GitService` 同步操作方法
  - `GitBridge` 槽
  - `RepoView` 菜单和危险确认
  - 覆盖真实 bare remote 的测试
- 验证:
  - 本地落后远端时覆盖成功
  - 本地有未提交改动时确认后被丢弃,取消则无变化
  - 无上游/分离 HEAD 时拒绝并提示
- Review 重点:
  - 禁止猜默认分支名
  - 禁止使用裸 `--force` 替代安全策略
  - 危险文案必须写明“丢弃本地未提交改动和本地未推送提交”

### Step 3: 分支与远程补全

- 目标:
  - 分支重命名。
  - 强制删除分支入口,走危险确认。
  - 设置/修改上游。
  - 远程分支检出为本地分支时流程明确。
  - 远程重命名。
- 产物:
  - `BranchView` 和 `RemoteDialog` 补齐入口
  - 后端方法和真实仓库测试
- 验证:
  - 已合并分支普通删除成功
  - 未合并分支普通删除失败,强制删除需确认
  - 设置上游后 ahead/behind 正确刷新
- Review 重点:
  - ref 名必须沿用 `_bad_ref` 校验
  - 当前分支删除/重命名边界必须明确

### Step 4: 历史与中途状态补全

- 目标:
  - rebase continue/abort/skip。
  - cherry-pick continue/abort。
  - revert continue/abort。
  - 合并冲突状态下入口聚合到冲突页。
- 产物:
  - 中途状态检测
  - 冲突页操作入口
  - 历史页错误提示改进
- 验证:
  - 构造真实冲突并验证 continue/abort/skip
  - 中止后工作树和 HEAD 回到预期状态
- Review 重点:
  - 不能静默吞掉冲突
  - 不能把中途状态误判为普通干净仓库

### Step 5: Stash、Tag、维护操作增强

- 目标:
  - stash 保存时支持 include untracked、keep index、查看内容、从 stash 创建分支。
  - tag 支持轻量/附注类型选择、删除远程 tag。
  - clean 支持 include ignored 的危险确认。
  - gc/prune/fetch 的状态提示统一。
- 产物:
  - 页面入口、后端封装、测试
- 验证:
  - stash 内容可查看,应用/恢复后文件状态正确
  - 本地和远程 tag 删除行为分开验证
  - clean 不误删未确认范围
- Review 重点:
  - 删除远程 tag 和 clean ignored 都必须二次确认

### Step 6: 高级 Git 功能

- 目标:
  - worktree 管理。
  - submodule 初始化/更新/同步。
  - LFS 状态提示和基础 pull/push。
  - bisect 向导。
- 处理原则:
  - 高级功能不挤进主工作流。
  - 以独立页面或向导承载,避免干扰新手路径。
- 验证:
  - 每类功能至少一个真实仓库端到端测试。

## 5. 完成定义

全部完成必须同时满足:

- `docs/git-operations-matrix.md` 中 P0/P1 项均为已实现或有明确延期理由。
- 每个已实现项都有源码入口、后端封装、真实 Git 行为验证。
- 危险操作均有二次确认和明确后果文案。
- QML selftest 通过。
- 本轮产生的每步改动均已 commit。
- 最终 review 没有 P0/P1 阻断问题。

## 6. 当前进度

| 步骤 | 状态 | 验证 |
|---|---|---|
| Step 0: 文档和计划落盘 | 已完成 | `git diff --check`, QML selftest |
| Step 1: 测试基座 | 已完成 | `.venv/Scripts/python.exe -m unittest discover -s tests -v` |
| Step 2: 远程覆盖本地 | 已完成 | `unittest` 真实 bare remote 场景, QML selftest |
| Step 3: 强制删除分支 UI | 已完成 | `unittest` 未合并分支场景, QML selftest |
| Step 4: 同步 remote/branch 选择 | 已完成 | `unittest` 显式 remote/branch 场景, QML selftest |
| Step 5: 分支/远程基础补全 | 已完成 | `unittest` 重命名/上游/远程重命名场景, QML selftest |
| Step 6: 历史/中途状态补全 | 已完成 | `unittest` rebase/cherry-pick/revert 真实冲突场景, QML selftest |
