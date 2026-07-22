# AI 提交规划器 v1.3.0 构建验证

> 验证日期：2026-07-22  
> 构建验证提交：`7cef1fd03ed49194cb99b6e70d51ed8250c247fd`
> 验证范围：全量测试、Windows 安装包、Windows/macOS 打包态 QML 启动与本地 AI 连接链

## 验证结论

v1.3.0 的 Windows standalone EXE 和 macOS `.app` 均已完成启动验证，Windows
安装包已完成构建、版本和哈希核对。两端的 AI 连接自检使用临时配置和动态回环端口模拟
Ollama 模型列表接口，证明打包程序能够读取隔离配置、加载 QML 并访问配置的本地模型端点。

该结论只覆盖打包、启动和连接路径，不代表任何真实本地或远程模型的生成质量、接受率、
失败率或延迟已经达到发布门槛。

## Windows 产物

Windows 应用产物基于提交
`7cef1fd03ed49194cb99b6e70d51ed8250c247fd` 完整重建，并使用下列同一 EXE
再次完成真实连接自检。

| 产物 | 版本 | 字节数 | SHA-256 |
|---|---:|---:|---|
| `build_dist/main_qml.dist/Gitora.exe` | `1.3.0.0` | 12,909,056 | `D49F16035D1F7072A92B7ABB5973DA0AC3D2744D16403ADCBD818B708BD5ADE4` |
| `dist_installer/Gitora-Setup-1.3.0.exe` | `1.3.0` | 45,435,769 | `90776B8AB0C3FF49A6FE8F2A15994263E1C8A8DD546E8D9863821A5F315C4A60` |

修正后的相对路径调用验证输出包含：

```text
[SELFTEST] QML 加载成功,rootObjects = 1
[SELFTEST] AI 连接检测成功: 连接成功，检测到 1 个本地模型
[SELFTEST] 打包态 AI 连接验证通过
```

## macOS 产物

GitHub Actions run
[`29884387085`](https://github.com/aki-riko/Gitora/actions/runs/29884387085)
在提交 `7cef1fd03ed49194cb99b6e70d51ed8250c247fd` 上完成，以下步骤均成功：

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
SELFTEST passed
```

下载后的 DMG 实物校验：

| 产物 | 字节数 | SHA-256 | UDIF 尾签名 |
|---|---:|---|---|
| `build_dist/macos-run-29884387085/Gitora-macOS.dmg` | 195,897,583 | `F5D576161D2BD3F0847A22E660BAF26A8DA976BFDB137F2C216930A694F93772` | `koly` |

GitHub artifact `Gitora-macOS-unsigned` 的归档大小为 183,344,896 字节，平台记录的
归档摘要为
`sha256:850d7dbacba666f9d4f6cf7f18c031c3044ed8aa74de063faa47b6e1489631fa`；
该摘要属于 artifact ZIP，不能与上表中的 DMG 文件摘要混用。

## 源码级回归

- 提交 `7cef1fd` 的本地全量测试结果为 `170 passed`。
- Cross-platform SELFTEST run
  [`29884149477`](https://github.com/aki-riko/Gitora/actions/runs/29884149477)
  在同一提交上的 Ubuntu 与 macOS job 均成功。
- 源码 QML 在全新进程中的 headless selftest 输出 `exit=0`，并检测到
  `rootObjects = 1`。

## 失败复现与修复证据

前一 run
[`29878569297`](https://github.com/aki-riko/Gitora/actions/runs/29878569297)
在同一 macOS 自检步骤用相对可执行路径复现失败：

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
