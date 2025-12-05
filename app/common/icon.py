# coding: utf-8
from enum import Enum

from qfluentwidgets import FluentIconBase, getIconColor, Theme


class Icon(FluentIconBase, Enum):

    # 设置图标
    SETTINGS = "Settings"
    SETTINGS_FILLED = "SettingsFilled"
    
    # Git专用图标
    GIT_BRANCH = "git-branch-line"
    GIT_MERGE = "git-merge-line"
    GIT_COMMIT = "git-commit-line"
    GIT_FORK = "git-fork-line"
    GIT_PULL_REQUEST = "git-pull-request-line"
    GIT_CLOSE_PR = "git-close-pull-request-line"
    GIT_REPOSITORY = "git-repository-line"
    GIT_REPOSITORY_COMMITS = "git-repository-commits-line"
    GIT_REPOSITORY_PRIVATE = "git-repository-private-line"
    GIT_PR_DRAFT = "git-pr-draft-line"

    def path(self, theme=Theme.AUTO):
        # 所有图标统一使用_black/_white后缀
        return f":/app/images/icons/{self.value}_{getIconColor(theme)}.svg"
