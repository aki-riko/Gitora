# Gitess - Git可视化工具

对新人友好的Git操作界面，基于PySide6和QFluentWidgets Pro开发。

## ✨ 特性

- 🎯 **新手友好** - 清晰直观的操作界面，一键暂存+提交+推送
- 🚀 **功能完善** - 文件差异、提交历史、分支管理、冲突解决、Stash管理
- 🎨 **美观现代** - 基于Fluent Design设计语言，支持亮色/暗色主题
- ⚡ **性能优化** - LRU缓存、虚拟滚动、异步操作
- 🔒 **安全可靠** - 危险操作二次确认，完整的错误处理

## 功能列表

### 核心功能
- ✅ 打开Git仓库
- ✅ 文件变更显示（实时刷新）
- ✅ 暂存/取消暂存（单个/全部）
- ✅ 文件差异显示（语法高亮）
- ✅ 提交/修改提交
- ✅ 推送/拉取（异步）
- ✅ 一键暂存+提交+推送

### 历史管理
- ✅ 提交历史时间线（分页加载）
- ✅ 提交搜索（按消息/作者）
- ✅ 撤销提交（Revert）
- ✅ 回滚到指定提交（Reset）
- ✅ LRU缓存优化

### 分支管理
- ✅ 本地/远程分支列表
- ✅ 创建/删除分支
- ✅ 切换分支
- ✅ 合并分支
- ✅ Fetch远程更新

### 冲突解决
- ✅ 自动检测合并冲突
- ✅ 显示冲突文件列表
- ✅ 使用ours/theirs解决
- ✅ 查看冲突内容（高亮显示）
- ✅ 中止合并

### Stash管理
- ✅ 保存到Stash
- ✅ 应用Stash（不删除）
- ✅ 恢复Stash（删除）
- ✅ 删除Stash
- ✅ 清空所有Stash

### 文件历史
- ✅ 查看文件提交历史
- ✅ 查看指定版本内容
- ✅ 对比两个版本
- ✅ 跟踪文件重命名

## 🚀 快速开始

### 环境要求

- Python 3.12+
- PySide6
- QFluentWidgets Pro 1.9.2+
- Git（系统安装）

### 安装

1. **安装依赖**
```bash
pip install -r requirements.txt
```

2. **配置License**

设置环境变量：
```bash
# Windows
set QFLUENTWIDGETS_PRO_LICENSE=your-license-key

# 或者在 %LOCALAPPDATA%\Gitess\license.key 创建文件
```

3. **运行应用**
```bash
python main.py
```

## 📁 项目结构
```
Gitess/
├── main.py                          # 应用入口
├── deploy.py                        # Nuitka打包脚本
├── requirements.txt                 # 依赖清单
├── README.md                        # 项目说明
├── README-License.md                # License配置说明
├── .gitignore                       # Git忽略规则
│
├── app/                             # 主程序
│   ├── common/                      # 公共模块
│   │   ├── config.py                # 配置管理
│   │   ├── git_service.py           # Git服务（876行）⭐
│   │   ├── icon.py                  # 自定义图标
│   │   ├── setting.py               # 常量定义
│   │   ├── signal_bus.py            # 信号总线
│   │   └── style_sheet.py           # 样式表
│   │
│   ├── resource/                    # 资源文件
│   │   ├── i18n/                    # 国际化
│   │   ├── images/                  # 图片资源
│   │   └── qss/                     # QSS样式
│   │       ├── dark/                # 暗色主题
│   │       └── light/               # 亮色主题
│   │
│   └── view/                        # UI界面
│       ├── main_window.py           # 主窗口（110行）
│       ├── repo_interface.py        # 仓库界面（818行）⭐
│       ├── history_interface.py     # 历史界面（751行）⭐
│       ├── branch_interface.py      # 分支界面（452行）
│       ├── conflict_interface.py    # 冲突界面（327行）
│       ├── stash_dialog.py          # Stash对话框（297行）
│       ├── file_history_dialog.py   # 文件历史对话框（169行）
│       ├── conflict_viewer_dialog.py # 冲突查看器（68行）
│       └── setting_interface.py     # 设置界面（185行）
│
└── docs/                            # 文档
    ├── 功能实现报告-2025-12-03.md
    ├── 前端UI开发完成报告-2025-12-03.md
    └── Tooltip统一Fluent风格-2025-12-03.md
```

## 🛠️ 技术栈

- **UI框架**: PySide6 6.5+
- **组件库**: QFluentWidgets Pro 1.9.2
- **Git操作**: subprocess + 异步QThread
- **架构模式**: MVC分层架构
- **信号驱动**: Qt信号槽机制

## 📊 代码统计

- **总代码量**: 7,188行
- **文件数量**: 17个Python文件
- **平均行数**: 422行/文件
- **最大文件**: git_service.py（876行）
- **代码质量**: ✅ 无TODO/FIXME，无静默异常

## 🎯 使用说明

### 1. 打开仓库
点击"打开仓库"按钮，选择一个Git仓库目录。

### 2. 文件变更
- 查看变更文件列表
- 点击文件查看差异（语法高亮）
- 点击"暂存"按钮暂存文件
- 右键文件可查看文件历史

### 3. 提交
- 输入提交信息
- 点击"提交"按钮
- 或使用"一键提交推送"（新手推荐）

### 4. 历史
- 查看提交历史时间线
- 搜索提交（按消息/作者）
- 撤销或回滚提交

### 5. 分支
- 查看本地和远程分支
- 创建、切换、合并、删除分支

### 6. 冲突
- 自动检测合并冲突
- 选择使用ours或theirs解决
- 查看冲突文件内容

### 7. Stash
- 点击"暂存管理"按钮
- 保存当前工作区到Stash
- 恢复或删除Stash

## 📝 开发文档

- [功能实现报告](docs/功能实现报告-2025-12-03.md)
- [前端UI开发完成报告](docs/前端UI开发完成报告-2025-12-03.md)
- [Tooltip统一Fluent风格](docs/Tooltip统一Fluent风格-2025-12-03.md)
- [License配置说明](README-License.md)

## 已知问题

- Windows系统需要Git命令行工具
- 大仓库首次加载可能较慢（已优化缓存）

## 技术支持

详见开发文档：
- [功能实现报告](docs/功能实现报告-2025-12-03.md)
- [前端UI开发完成报告](docs/前端UI开发完成报告-2025-12-03.md)