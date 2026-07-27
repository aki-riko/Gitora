# AI 提交规划器 v1.3.0 构建验证

> 验证日期：2026-07-22
> 应用代码提交：`21e0030edba6570f5b4bbfda761878faf62eb2d0`
> 验证范围：全量测试、Windows 安装包、Windows Credential Manager、macOS Keychain、两端打包态 QML、设置页导航与本地 AI 连接链

## 验证结论

v1.3.0 的最终代码已完成源码回归和 Windows/macOS 打包态验证。图形界面只提供系统凭据
持久化入口，不提供进程生命周期内的临时密钥路径；用户在设置页输入的远程 API Key 默认且
唯一写入当前用户的操作系统凭据库，普通配置文件不保存密钥。环境变量只作为外部自动化
兼容回退，Gitora 不会替用户写入环境变量。

Windows standalone 与 macOS `.app` 均使用唯一临时凭据完成原生系统凭据写入、读取、
删除和删除确认，同时完成真实设置页导航和动态回环 Ollama 连接。两端构建使用
`prismqml 0.3.1.32` 与 `keyring 25.7.0`，`pip check` 报告
`No broken requirements found.`。

该结论证明凭据持久化、打包、启动、导航和连接链可用，不代表真实模型的生成质量、接受率、
失败率或延迟已经达到发布门槛。

## 系统凭据存储边界

- Windows 直接实例化 `keyring.backends.Windows.WinVaultKeyring`，持久级别固定为
  `CRED_PERSIST_LOCAL_MACHINE`，凭据由当前用户的 Windows Credential Manager/DPAPI
  保护，不是进程内、退出即失效或当前登录会话级存储。
- macOS 直接实例化 `keyring.backends.macOS.Keyring`，使用当前用户默认 Keychain。
- 不调用 keyring 自动后端选择，不允许 `keyrings.alt`、明文文件或其他降级后端。
- 密钥不进入 `ai_commit.json`、日志或崩溃信息；Bridge 和凭据封装也不缓存密钥。
- 凭据按提供方和精确端点的 SHA-256 摘要隔离，系统凭据条目不暴露完整端点。
- 系统凭据优先于配置的环境变量。原生凭据操作失败时，设置页显示明确错误；不会把密钥
  回退写入普通配置。

## Windows 产物

Windows 应用和安装包均从应用代码提交
`21e0030edba6570f5b4bbfda761878faf62eb2d0` 完整重建。

| 产物 | 版本 | 字节数 | SHA-256 |
|---|---:|---:|---|
| `build_dist/main_qml.dist/Gitora.exe` | `1.3.0.0` | 19,461,632 | `E0A16FDB04EDBA5576AB3DAD279A1BCD8CF0A44DF31D74508539C3F050E9F126` |
| `dist_installer/Gitora-Setup-1.3.0.exe` | `1.3.0` | 47,103,806 | `6810AE7220C8B8DAFED613DE159DF6967177FB4DF6470312D7962305B8EBC27C` |

最终 `Gitora.exe` 的打包态自检输出包含：

```text
[SELFTEST] QML 加载成功,rootObjects = 1
[SELFTEST] 系统凭据库验证阶段: 初始化原生后端
[SELFTEST] 系统凭据库验证阶段: 写入临时凭据
[SELFTEST] 系统凭据库验证阶段: 读取临时凭据
[SELFTEST] 系统凭据库验证阶段: 删除临时凭据
[SELFTEST] 系统凭据库验证阶段: 确认临时凭据已删除
[SELFTEST] 系统凭据库验证成功: 原生系统凭据写入、读取和删除均通过
[SELFTEST] AI 连接检测成功: 连接成功，检测到 1 个本地模型
[SELFTEST] 设置页导航成功: SettingsView 已加载
[SELFTEST] 打包态 AI 连接验证通过
```

该验证使用最终 EXE 真实访问 Windows Credential Manager，并在读取确认后删除唯一临时
条目。Windows 单元测试还直接断言后端持久级别等于 `CRED_PERSIST_LOCAL_MACHINE`，且
不等于 `CRED_PERSIST_SESSION`。

## macOS 产物

GitHub Actions run
[`29913064263`](https://github.com/aki-riko/Gitora/actions/runs/29913064263)
的 job `88900352288` 在应用代码提交
`21e0030edba6570f5b4bbfda761878faf62eb2d0` 上完成，用时 9 分 22 秒。以下步骤均成功：

- Nuitka 构建 `.app`；
- ad-hoc 重签并通过 `codesign --verify --deep`；
- 创建压缩 UDIF DMG；
- 执行打包态 AI 连接、设置页导航和 Keychain 自检；
- 上传 DMG 与 `.app` artifact；
- 因未提供 `release_tag`，附加到 Release 的步骤按预期跳过。

CI 日志包含完整 Keychain 验收链：

```text
[SELFTEST] 系统凭据库验证阶段: 初始化原生后端
[SELFTEST] 系统凭据库验证阶段: 写入临时凭据
[SELFTEST] 系统凭据库验证阶段: 读取临时凭据
[SELFTEST] 系统凭据库验证阶段: 删除临时凭据
[SELFTEST] 系统凭据库验证阶段: 确认临时凭据已删除
[SELFTEST] 系统凭据库验证成功: 原生系统凭据写入、读取和删除均通过
[SELFTEST] AI 连接检测成功: 连接成功，检测到 1 个本地模型
[SELFTEST] 设置页导航成功: SettingsView 已加载
[SELFTEST] 打包态 AI 连接验证通过
SELFTEST passed
```

下载后的 DMG 实物校验：

| 产物 | 字节数 | SHA-256 | UDIF footer 签名 |
|---|---:|---|---|
| `Gitora-macOS.dmg` | 198,580,389 | `78079005994818F56701BC4A77E1D4D0619044326F639C9D3E994BD3837AD3CF` | `koly` |

GitHub artifact `Gitora-macOS-unsigned` 的 ID 为 `8526924092`，归档大小为
185,027,972 字节，GitHub 记录的归档摘要为
`sha256:3c1c323280b860510aa8c57903faa451b7a2fc3d610ac3804c489730838c04d2`。
该摘要属于 artifact ZIP，不能与上表中的 DMG 本体 SHA-256 混用。

## 源码级回归

- 最终全量测试：`188 passed in 198.50s`。
- 凭据、Bridge、QML 合同、设置和打包自检专项测试：`44 passed in 14.13s`。
- Windows 原生凭据 round-trip 测试使用唯一 service/account 完成写入、读取和删除。
- `keyring` 版本通过 `importlib.metadata.version("keyring")` 核对为 `25.7.0`。
- `prismqml.__version__` 核对为 `0.3.1.32`。
- `pip check` 无损坏依赖。

大型 REVIEW 另外补齐了两条失败路径：原生后端对象创建后若实际读取失败，Bridge 会把凭据库
标记为不可用并向设置页暴露脱敏错误；打包自检若后端声称删除成功但仍可读到临时凭据，
`finally` 会再次执行清理。对应回归先复现失败，再在应用代码提交 `21e0030` 中修复并通过。

## 设置页失败复现与修复证据

修复前 Gitora 独立 venv 和需求约束均停留在 `prismqml 0.3.1.15`。升级到 PyPI 正式版
`0.3.1.32` 后，使用同一条真实设置页导航路径仍复现：

```text
SettingsView.qml:166:13: AiCommitSettingsCard is not a type
```

这证明“引擎未更新”和“设置页打不开”是两条独立问题。设置页位于 `qml/views/`，但引用
`qml/components/AiCommitSettingsCard.qml` 时遗漏 `import "../components"`。补齐导入后，
Windows standalone 与最终 macOS `.app` 均通过真实 `currentIndex` 切换和懒加载栈状态确认
设置页已加载并显示，同一路径不再出现原错误。

## 本机模型代理边界

大型审查曾用真实回环目标和代理捕获器复现：明确回环的 Ollama 请求会读取环境代理。修复后，
仅明确回环端点使用空 `ProxyHandler`；非回环 Ollama 和远程 Responses 仍保留环境代理能力。
当前全量回归继续使用同一目标/代理拓扑确认代理捕获列表为空、目标服务收到
`GET /v1/models`。

## 自检隔离与隐私

- Windows 自检把 `LOCALAPPDATA` 和 `HOME` 指向临时目录。
- macOS 必须保留真实 `HOME`，以保持当前用户默认 Keychain 上下文；Gitora 配置改由临时
  `XDG_CONFIG_HOME` 隔离。此前覆盖 macOS `HOME` 的真实失败会让 Keychain 写入卡住，
  最终 run 已用修正后的同一路径通过。
- 系统凭据自检使用 `Gitora.AiCommit.Selftest.<UUID>` 和随机密钥，不读取、覆盖或删除用户
  已保存的 Gitora 凭据。
- Ollama stub 只监听动态分配的 `127.0.0.1` 端口，不访问公网、不使用真实 API Key，且不
  发送仓库源码。

## 尚未验证的事项

- 当前验证环境未配置真实 Ollama 模型或远程 Responses API Key，尚无真实模型质量、接受率、
  失败率和端到端延迟结论。
- Windows 安装器尚未执行完整安装、升级和卸载流程；当前验证到安装包生成、版本和哈希。
- headless/offscreen 验证确认设置页真实加载，但不替代用户对窗口视觉效果的主观验收。
- macOS DMG 使用 ad-hoc 签名，未做 Apple Developer ID 签名或公证。
- 本轮未创建 `v1.3.0` tag，也未创建 GitHub Release。
