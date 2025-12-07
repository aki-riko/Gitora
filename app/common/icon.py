# coding: utf-8
from enum import Enum

from qfluentwidgets import FluentIconBase, getIconColor, Theme


class Icon(FluentIconBase, Enum):

    # Git专用图标
    GIT_BRANCH = "git-branch"              # 分支
    GIT_MERGE = "git-merge"                # 合并
    GIT_COMMIT = "git-commit"              # 提交/检出
    GIT_COMPARE = "git-compare"            # 比较
    GIT_FORK = "git-fork"                  # 分叉/冲突
    GIT_FETCH = "git-fetch"                # 获取远程
    GIT_CHERRY_PICK = "git-cherry-pick"    # 应用提交
    GIT_PULL_REQUEST = "git-pull-request"  # 拉取请求
    GIT_PR_CLOSED = "git-pull-request-closed"   # 关闭的PR
    GIT_PR_DRAFT = "git-pull-request-draft"     # 草稿/Stash
    GIT_STASH_APPLY = "git-stash-apply"    # 应用储藏
    GIT_STASH_POP = "git-stash-pop"        # 恢复储藏
    GIT_REPOSITORY = "git-repository"      # 仓库
    GIT_REPOSITORY_COMMITS = "git-repository-commits"  # 提交历史
    GITHUB = "github"                      # GitHub

    def path(self, theme=Theme.AUTO):
        # 所有图标统一使用_black/_white后缀
        return f":/app/images/icons/{self.value}_{getIconColor(theme)}.svg"
