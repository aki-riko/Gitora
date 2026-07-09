# Git 操作功能矩阵

> 创建日期: 2026-07-09
> 用途: 作为 Gitora 补全 Git 操作的范围、现状和验收依据。

## 状态图例

- 已有: 源码中已有用户入口和后端调用。
- 部分: 已有一部分能力,但入口、边界或测试不完整。
- 缺失: 当前未发现入口或封装。
- 高级: 不属于新手高频路径,后续独立设计。

## 现有入口核对

| 领域 | 操作 | 状态 | 已验证源码入口 | 后续要求 |
|---|---|---:|---|---|
| 仓库 | 打开仓库 | 已有 | `RepoView.openButton`, `GitBridge.openRepoAsync` | 保持最近仓库和扫描结果去重 |
| 仓库 | 克隆 | 已有 | `CloneDialog`, `GitBridge.clone`, `GitService.clone` | 增加 clone 后自动打开的失败提示复核 |
| 仓库 | 初始化 | 已有 | `InitRepoGuide`, `GitBridge.initRepo` | 保持远程可选配置 |
| 仓库 | 最近仓库管理 | 部分 | `getRecentRepos/removeRecentRepo/clearRecentRepos` | 需要 UI 管理入口复核 |
| 工作区 | 查看状态 | 已有 | `requestStatus`, `statusReady` | 继续保持异步和过期结果丢弃 |
| 工作区 | 查看 diff | 已有 | `requestDiff`, `diffReady` | 后续可补 side-by-side 视图 |
| 工作区 | 暂存文件 | 已有 | `GitBridge.stageFile` | 真实仓库回归测试 |
| 工作区 | 取消暂存文件 | 已有 | `GitBridge.unstageFile` | 真实仓库回归测试 |
| 工作区 | 全部暂存 | 已有 | `GitBridge.stageAll` | 真实仓库回归测试 |
| 工作区 | 全部取消暂存 | 已有 | `GitBridge.unstageAll` | 真实仓库回归测试 |
| 工作区 | 丢弃文件改动 | 已有 | `RepoView.discardDanger`, `GitBridge.discardFile` | 保持危险确认 |
| 工作区 | clean 未跟踪文件 | 已有 | `CleanDialog`, `requestCleanPreview`, `clean` | 补 include ignored 的独立危险确认 |
| 提交 | 普通提交 | 已有 | `RepoView.commit`, `GitBridge.commit` | 测试空消息/无变更提示 |
| 提交 | amend | 已有 | `RepoView.amendDanger`, `GitBridge.amendCommit` | 已推送 HEAD 告警继续保留 |
| 提交 | 一键提交推送 | 已有 | `quickCommitPush` | 补失败阶段的分步错误测试 |
| 同步 | fetch | 已有 | `fetchRemote(remote)`, `syncDialog` | 已支持选择 remote |
| 同步 | pull | 已有 | `pullFrom(remote, branch)`, `syncDialog` | 已支持选择 remote/branch |
| 同步 | pull --rebase | 已有 | `pullRebaseFrom(remote, branch)`, `syncDialog` | 已支持选择 remote/branch |
| 同步 | push | 已有 | `pushTo(remote, branch)`, `syncDialog` | 已支持选择 remote/branch |
| 同步 | force push | 已有 | `pushForceTo(remote, branch)`, `forcePushDanger` | 继续使用 `--force-with-lease`,已支持选择 remote/branch |
| 同步 | 远程强制覆盖本地 | 已有 | `forceResetToUpstream`, `force_reset_to_upstream_sync` | 支持当前分支上游,已走危险确认 |
| 同步 | 设置上游推送 | 部分 | `GitService.push_with_upstream`, `set_upstream` | 暴露到 UI 并测试 |
| 分支 | 列出本地/远程分支 | 已有 | `requestBranches`, `BranchView` | 保持 ahead/behind 显示 |
| 分支 | 创建并切换 | 已有 | `createBranch(name, true)` | 增加“不切换创建”选项可选 |
| 分支 | 切换本地分支 | 已有 | `checkoutBranch` | 脏工作区失败提示复核 |
| 分支 | 检出远程分支 | 部分 | `checkoutBranch(model.name)` | 明确创建本地跟踪分支流程 |
| 分支 | 删除分支 | 已有 | `deleteBranch(name, false)` | 补强制删除入口和危险确认 |
| 分支 | 强制删除分支 | 已有 | `deleteBranch(name, true)`, `forceDeleteBranchDanger` | 已走危险确认 |
| 分支 | 合并分支 | 已有 | `mergeBranch` | 冲突时进入冲突页提示 |
| 分支 | 分支重命名 | 已有 | `renameBranch`, `rename_branch` | 已支持本地分支重命名 |
| 分支 | 设置/修改上游 | 已有 | `setUpstream`, `set_upstream` | 已支持 remote/branch 输入 |
| 分支 | rebase 到目标分支 | 已有 | `rebaseOnto`, `rebase_onto`, `rebaseDanger` | 已走危险确认 |
| 分支 | rebase continue/abort/skip | 已有 | `continueRebase`, `abortRebase`, `skipRebase` | 冲突页聚合入口 |
| 远程 | 查看远程 | 已有 | `getRemoteInfo`, `RemoteDialog` | 保持 URL 安全校验 |
| 远程 | 添加远程 | 已有 | `addRemote` | 保持 `_bad_url` 校验 |
| 远程 | 修改远程 URL | 已有 | `setRemoteUrl` | 保持 `_bad_url` 校验 |
| 远程 | 删除远程 | 已有 | `removeRemote` | 二次确认已存在 |
| 远程 | prune | 已有 | `pruneRemote` | 支持选择 remote |
| 远程 | 重命名远程 | 已有 | `renameRemote`, `rename_remote` | 只修改本地远程配置 |
| 历史 | 分页日志 | 已有 | `requestLog` | 保持大仓库虚拟滚动 |
| 历史 | 搜索提交 | 已有 | `requestSearch` | 测试作者/消息/hash |
| 历史 | 提交详情 | 已有 | `CommitDetailDialog` | 可补文件列表排序 |
| 历史 | checkout commit | 已有 | `checkoutCommit` | 分离 HEAD 提示复核 |
| 历史 | cherry-pick | 已有 | `cherryPick`, `continueCherryPick`, `abortCherryPick` | 已支持冲突 continue/abort |
| 历史 | revert | 已有 | `revertCommit`, `continueRevert`, `abortRevert` | 已支持冲突 continue/abort |
| 历史 | reset soft/mixed/hard | 已有 | `HistoryView.resetDanger`, `resetToCommit` | hard 文案继续明确丢弃 |
| 历史 | 复制 hash | 已有 | `ClipboardHelper.copy` | 保持轻量入口 |
| 历史 | reflog | 已有 | `ReflogDialog`, `requestReflog` | 可补 reset/branch from reflog |
| Stash | 保存 | 已有 | `stashSave` | 补 include untracked/keep index |
| Stash | apply | 已有 | `stashApply` | 冲突提示复核 |
| Stash | pop | 已有 | `stashPop` | 冲突提示复核 |
| Stash | drop | 部分 | `stashDrop` | 补危险确认 |
| Stash | clear | 部分 | `stashClear` | 补危险确认 |
| Stash | show 内容 | 缺失 | 未发现 | P1 |
| Stash | 从 stash 建分支 | 缺失 | 未发现 | P2 |
| Tag | 列出 tag | 已有 | `requestTags` | 保持异步 |
| Tag | 创建 tag | 已有 | `createTag` | 区分轻量/附注 tag |
| Tag | checkout tag | 已有 | `checkoutTag` | 分离 HEAD 提示复核 |
| Tag | 删除本地 tag | 部分 | `deleteTag` | 补危险确认 |
| Tag | 推送单个 tag | 已有 | `pushTag` | 真实远端测试 |
| Tag | 推送全部 tag | 已有 | `pushAllTags` | 真实远端测试 |
| Tag | 删除远程 tag | 缺失 | 后端有 `delete_remote_tag`, UI 未接 | P1 |
| 冲突 | 检测中途操作状态 | 已有 | `getConflictOperation`, `requestConflicts` | 已扩展到 merge/rebase/cherry-pick/revert |
| 冲突 | 查看冲突文件 | 已有 | `ConflictViewerDialog` | 保持路径越界保护 |
| 冲突 | ours | 已有 | `resolveWithOurs` | 真实冲突测试 |
| 冲突 | theirs | 已有 | `resolveWithTheirs` | 真实冲突测试 |
| 冲突 | abort 中途操作 | 已有 | `abortMerge`, `abortRebase`, `abortCherryPick`, `abortRevert` | 冲突页聚合入口 |
| 维护 | gc | 已有 | `GitBridge.gc` | 操作反馈统一 |
| 维护 | clean preview | 已有 | `requestCleanPreview` | 预览必须来自真实 Git 输出 |
| 高级 | worktree | 高级 | 未发现 | P2 独立设计 |
| 高级 | submodule | 高级 | 未发现 | P2 独立设计 |
| 高级 | LFS | 高级 | 未发现 | P2 独立设计 |
| 高级 | bisect | 高级 | 未发现 | P2 独立设计 |

## 危险操作策略

以下操作必须使用 `DangerDialog` 或同级二次确认:

- `reset --hard`
- 远程强制覆盖本地
- 强制推送
- 强制删除分支
- 删除远程
- 删除 tag,尤其远程 tag
- stash clear/drop
- clean,尤其 include ignored

危险确认文案必须包含:

- 会影响什么对象。
- 是否会丢弃未提交改动。
- 是否会重写历史或覆盖远端。
- 是否可恢复。

## 验收用真实仓库场景

后续实现不能只用 mock。至少准备这些临时仓库场景:

| 场景 | 用途 |
|---|---|
| 单本地仓库 | stage/commit/reset/reflog/tag/stash |
| bare remote + 两个 clone | push/pull/fetch/force-with-lease/ahead/behind |
| 本地落后远端 | pull 和远程覆盖本地 |
| 本地领先远端 | push 和 force push |
| 本地和远端分叉 | merge/rebase/冲突处理 |
| 未合并分支 | 普通删除失败和强制删除确认 |
| 冲突工作区 | merge/rebase/cherry-pick/revert continue/abort |
| 含未跟踪和 ignored 文件 | stash include untracked/clean ignored |
| 含本地和远程 tag | tag 推送和删除 |

## 当前优先级

已完成 P0:

- 测试基座。
- 远程强制覆盖本地。
- 强制删除分支 UI。

剩余 P0:

- 无。

已完成 P1:

- 分支重命名、设置上游、远程重命名。
- rebase 到目标分支、rebase continue/abort/skip、cherry-pick/revert continue/abort。

剩余 P1:

- stash 和 tag 安全增强。

P2:

- worktree、submodule、LFS、bisect。
- 更高级的 diff 和比较体验。
