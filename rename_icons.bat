@echo off
chcp 65001 >nul
echo ========================================
echo 重命名图标文件
echo ========================================
echo.
echo 将 (1).svg 重命名为 _white.svg
echo 将 .svg 重命名为 _black.svg
echo.

cd app\resource\images\icons

echo 重命名Git图标...

ren "git-branch-line (1).svg" "git-branch-line_white.svg"
ren "git-branch-line.svg" "git-branch-line_black.svg"

ren "git-close-pull-request-line (1).svg" "git-close-pull-request-line_white.svg"
ren "git-close-pull-request-line.svg" "git-close-pull-request-line_black.svg"

ren "git-commit-line (1).svg" "git-commit-line_white.svg"
ren "git-commit-line.svg" "git-commit-line_black.svg"

ren "git-fork-line (1).svg" "git-fork-line_white.svg"
ren "git-fork-line.svg" "git-fork-line_black.svg"

ren "git-merge-line (1).svg" "git-merge-line_white.svg"
ren "git-merge-line.svg" "git-merge-line_black.svg"

ren "git-pr-draft-line (1).svg" "git-pr-draft-line_white.svg"
ren "git-pr-draft-line.svg" "git-pr-draft-line_black.svg"

ren "git-pull-request-line (1).svg" "git-pull-request-line_white.svg"
ren "git-pull-request-line.svg" "git-pull-request-line_black.svg"

ren "git-repository-commits-line (1).svg" "git-repository-commits-line_white.svg"
ren "git-repository-commits-line.svg" "git-repository-commits-line_black.svg"

ren "git-repository-line (1).svg" "git-repository-line_white.svg"
ren "git-repository-line.svg" "git-repository-line_black.svg"

ren "git-repository-private-line (1).svg" "git-repository-private-line_white.svg"
ren "git-repository-private-line.svg" "git-repository-private-line_black.svg"

cd ..\..\..\..

echo.
echo 重命名完成！
echo.
pause
