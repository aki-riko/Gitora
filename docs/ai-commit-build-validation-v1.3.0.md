# AI 提交规划器 v1.3.0 构建验证

> 验证日期：2026-07-22
> 构建验证提交：`d6c9f5961411a02ee0eec68d16e85f1d4d859cae`
> 验证范围：全量测试、Windows 安装包、Windows/macOS 打包态 QML 启动、设置页导航与本地 AI 连接链

## 验证结论

v1.3.0 的 Windows standalone EXE 和 macOS `.app` 均已完成启动与设置页导航验证，Windows
安装包已完成构建、版本和哈希核对。两端的 AI 连接自检使用临时配置和动态回环端口模拟
Ollama 模型列表接口，证明打包程序能够读取隔离配置、加载 QML、实际创建并显示设置页，
以及访问配置的本地模型端点。两端构建均使用 `prismqml 0.3.1.32`。

该结论只覆盖打包、启动和连接路径，不代表任何真实本地或远程模型的生成质量、接受率、
失败率或延迟已经达到发布门槛。

## Windows 产物

Windows 应用产物基于提交
`d6c9f5961411a02ee0eec68d16e85f1d4d859cae` 完整重建，并使用下列同一 EXE
再次完成真实连接自检。

| 产物 | 版本 | 字节数 | SHA-256 |
|---|---:|---:|---|
| `build_dist/main_qml.dist/Gitora.exe` | `1.3.0.0` | 13,022,208 | `E7F0F71132ED35BC63E9CBCC3AD3EBAB6431B61069DAD547C2BB0DE6838F996B` |
| `dist_installer/Gitora-Setup-1.3.0.exe` | `1.3.0` | 45,464,494 | `20D793704E025C2A9E49360C9643A75A3AC417FD7A10C9CBB1C87B27661DD790` |

构建所用独立 venv 报告 `prismqml=0.3.1.32`，重建后的 `Gitora.exe` 二进制中也可
检出同一版本字符串。打包命令由该 venv 的 Python 执行，旧版引擎未进入新产物。

修正后的相对路径调用验证输出包含：

```text
[SELFTEST] QML 加载成功,rootObjects = 1
[SELFTEST] AI 连接检测成功: 连接成功，检测到 1 个本地模型
[SELFTEST] 设置页导航成功: SettingsView 已加载
[SELFTEST] 打包态 AI 连接验证通过
```

## macOS 产物

GitHub Actions run
[`29901858450`](https://github.com/aki-riko/Gitora/actions/runs/29901858450)
的 job `88864177755` 在提交 `d6c9f5961411a02ee0eec68d16e85f1d4d859cae` 上完成，
以下步骤均成功：

- Nuitka 构建 `.app`；
- ad-hoc 重签并通过 `codesign --verify --deep`；
- 创建压缩 UDIF DMG；
- 执行打包态 AI 连接与 headless QML 自检；
- 上传 DMG 和 `.app` artifact；
- 因未提供 `release_tag`，附加到 Release 的步骤按预期跳过。

CI 日志包含以下验收标志：

```text
签名校验通过
[SELFTEST] QML 加载成功,rootObjects = 1
[SELFTEST] AI 连接检测成功: 连接成功，检测到 1 个本地模型
[SELFTEST] 设置页导航成功: SettingsView 已加载
[SELFTEST] 打包态 AI 连接验证通过
SELFTEST passed
```

下载后的 DMG 实物校验：

| 产物 | 字节数 | SHA-256 | UDIF 尾签名 |
|---|---:|---|---|
| `build_dist/macos-run-29901858450/Gitora-macOS.dmg` | 197,677,822 | `C5931074C5AEB094C749F0A4CC4A67D32A45B8C7FF4C89E9728F210750CB08A4` | `koly` |

GitHub artifact `Gitora-macOS-unsigned`（artifact ID `8522389674`）的归档大小为
183,567,991 字节，平台记录和下载实物共同核对的
归档摘要为
`sha256:cbe72c235c49805c7a5436fa05347d9576901d8efc13c620166cf9e202cfb985`；
该摘要属于 artifact ZIP，不能与上表中的 DMG 文件摘要混用。

## 源码级回归

- 提交 `d6c9f59` 的本地全量测试结果为 `173 passed in 203.07s`。
- Cross-platform SELFTEST run
  [`29901486587`](https://github.com/aki-riko/Gitora/actions/runs/29901486587)
  在同一提交上的 Ubuntu 与 macOS job 均成功。
- 源码 QML 在全新进程中的 headless selftest 输出 `exit=0`，并检测到
  `rootObjects = 1` 和 `设置页导航成功: SettingsView 已加载`。

## 设置页失败复现与修复证据

修复前 Gitora 独立 venv 和需求约束均停留在 `prismqml 0.3.1.15`。升级到 PyPI
正式版 `0.3.1.32` 后，使用同一条真实设置页导航路径仍复现以下错误：

```text
SettingsView.qml:166:13: AiCommitSettingsCard is not a type
```

这证明引擎未更新和设置页打不开是两条独立问题。设置页位于 `qml/views/`，但使用
`qml/components/AiCommitSettingsCard.qml` 时遗漏 `import "../components"`。补齐导入后，
源码进程、Windows standalone、macOS `.app` 以及 Ubuntu/macOS 跨平台自检均用真实
`currentIndex` 切换和懒加载栈状态确认设置页已加载并显示；原错误在同一路径中不再出现。

## 本机模型代理泄露复现与修复证据

大型审查发现，明确回环的 Ollama 端点虽然不需要远程发送确认，但 Python `urllib` 默认会
读取环境代理。修复前使用两个真实回环 HTTP 服务分别作为 Ollama 目标和代理捕获器，设置
`HTTP_PROXY=http://127.0.0.1:<动态端口>` 且清空 `NO_PROXY` 后，发往
`127.0.0.1` 的模型列表请求会被代理捕获，违反“本机模型不经过第三方网络路径”的边界。

提交 `d6c9f59` 让仅限明确回环端点的 Ollama 客户端使用空 `ProxyHandler`，非回环 Ollama
和远程 Responses 端点仍保留环境代理能力。回归测试用同一目标/代理拓扑确认代理捕获列表
为空，同时目标服务收到 `GET /v1/models`。最终 Windows EXE 又在以下环境中完成打包态
自检并退出 0：

```text
HTTP_PROXY=http://127.0.0.1:9
NO_PROXY=
[SELFTEST] QML 加载成功,rootObjects = 1
[SELFTEST] AI 连接检测成功: 连接成功，检测到 1 个本地模型
[SELFTEST] 设置页导航成功: SettingsView 已加载
[SELFTEST] 打包态 AI 连接验证通过
```

## 打包自检路径失败复现与修复证据

前一 run
[`29878569297`](https://github.com/aki-riko/Gitora/actions/runs/29878569297)
曾在 macOS 自检步骤用相对可执行路径复现失败：

```text
[Errno 2] No such file or directory: 'build_dist/main_qml.app/Contents/MacOS/Gitora'
```

根因是自检工具在切换子进程工作目录后仍传递相对可执行路径。提交 `97e9ef5` 在切换工作
目录前严格解析绝对路径，并增加相对路径回归测试。最终 run `29884387085` 包含该修复并
使用同一工作流输入通过该步骤，构成同类真实失败输入的修复后验证。

## 隔离与隐私边界

- 自检创建临时 `HOME` 和 `LOCALAPPDATA`，不读取或覆盖用户的 AI 配置。
- stub 只监听动态分配的 `127.0.0.1` 端口，不访问公网，也不使用真实 API 密钥。
- 验证必须同时看到非零 `rootObjects`、AI 连接成功标志，并确认打包程序实际访问过
  回环 `/v1/models` 端点。
- 自检不发送仓库源码；回环响应只返回固定测试模型名。

## 尚未验证的事项

- 当前验证环境没有配置真实 Ollama 模型或远程 Responses 模型。
- 尚未产生真实模型的标题质量、拆分接受率、失败率和端到端延迟结论。
- Windows 安装器尚未执行完整安装、升级和卸载流程；当前只验证安装包生成、版本和哈希。
- macOS DMG 使用 ad-hoc 签名，未做 Apple Developer ID 签名或公证。
- 本次只完成构建与 artifact 验证，未创建 `v1.3.0` tag，也未创建 GitHub Release。
