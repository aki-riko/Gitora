# AI 提交规划器 v1.3.0 构建验证

> 验证日期：2026-07-22  
> 构建验证提交：`32f66b17a8a4b125e80930be98e3dfd43effc7f4`
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
`32f66b17a8a4b125e80930be98e3dfd43effc7f4` 完整重建，并使用下列同一 EXE
再次完成真实连接自检。

| 产物 | 版本 | 字节数 | SHA-256 |
|---|---:|---:|---|
| `build_dist/main_qml.dist/Gitora.exe` | `1.3.0.0` | 13,021,184 | `AAC24A226AC233BDA30A1B736E15B18C6C5314D9BA7FC59FADC52680A1A5CC3C` |
| `dist_installer/Gitora-Setup-1.3.0.exe` | `1.3.0` | 45,454,879 | `78F7444F552476245781B5DDEFEFCB13E6C6580D2BCBD1599F867AD23E5157BB` |

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
[`29899423160`](https://github.com/aki-riko/Gitora/actions/runs/29899423160)
在提交 `32f66b17a8a4b125e80930be98e3dfd43effc7f4` 上完成，以下步骤均成功：

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
| `build_dist/macos-run-29899423160/Gitora-macOS.dmg` | 197,782,734 | `A30B0C33CFE7B9F6FA33669B5F60B48E26A52EC6000CE6F912146EBBCE7AA06C` | `koly` |

GitHub artifact `Gitora-macOS-unsigned` 的归档大小为 183,733,704 字节，平台记录的
归档摘要为
`sha256:1075dd734464c698107a2d25de8462c7072105e27b276adce758609f3490b709`；
该摘要属于 artifact ZIP，不能与上表中的 DMG 文件摘要混用。

## 源码级回归

- 提交 `32f66b1` 的本地全量测试结果为 `172 passed`。
- Cross-platform SELFTEST run
  [`29899395493`](https://github.com/aki-riko/Gitora/actions/runs/29899395493)
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
