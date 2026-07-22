# AI 提交规划器 v1.3.0 构建验证

> 验证日期：2026-07-22  
> macOS 验证提交：`97e9ef588a5c5b597bc695629b702118d8babd18`  
> 验证范围：Windows 安装包、Windows/macOS 打包态 QML 启动与本地 AI 连接链

## 验证结论

v1.3.0 的 Windows 和 macOS 打包产物均已完成启动验证。两端的 AI
连接自检使用临时配置和动态回环端口模拟 Ollama 模型列表接口，证明打包程序能够读取
隔离配置、加载 QML 并访问配置的本地模型端点。

该结论只覆盖打包、启动和连接路径，不代表任何真实本地或远程模型的生成质量、接受率、
失败率或延迟已经达到发布门槛。

## Windows 产物

Windows 应用产物基于提交
`986ec9b2421523512c986060564757b07a4a7526` 完整重建。之后的
`97e9ef5` 只修改外部自检工具及其测试，不改变安装包中的应用载荷；修正后的工具已再次
使用下列同一 EXE 完成真实连接自检。

| 产物 | 版本 | 字节数 | SHA-256 |
|---|---:|---:|---|
| `build_dist/main_qml.dist/Gitora.exe` | `1.3.0.0` | 12,851,200 | `6E53A89DD81B1F28C1A0F6640502F0FE64EBCCD93CFEE3318D48E20045EF57D5` |
| `dist_installer/Gitora-Setup-1.3.0.exe` | `1.3.0` | 45,437,553 | `D38731FBB9E9B6537BEE184E496CAF79F2299F82AFAC01FC998F331018943CCC` |

修正后的相对路径调用验证输出包含：

```text
[SELFTEST] QML 加载成功,rootObjects = 1
[SELFTEST] AI 连接检测成功: 连接成功，检测到 1 个本地模型
[SELFTEST] 打包态 AI 连接验证通过
```

## macOS 产物

GitHub Actions run
[`29879070674`](https://github.com/aki-riko/Gitora/actions/runs/29879070674)
在提交 `97e9ef588a5c5b597bc695629b702118d8babd18` 上完成，以下步骤均成功：

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
| `build_dist/macos-run-29879070674/Gitora-macOS.dmg` | 197,332,093 | `6252CF1144C897CC856BE72D8DAE4450DA8C47E8E717C389300C3F6C3495271A` | `koly` |

GitHub artifact `Gitora-macOS-unsigned` 的归档大小为 183,348,683 字节，平台记录的
归档摘要为
`sha256:d340fd4efa1a6be2e654649fbf3c04fb084236e6b9f1ea7eda04f157e720c928`；
该摘要属于 artifact ZIP，不能与上表中的 DMG 文件摘要混用。

## 失败复现与修复证据

前一 run
[`29878569297`](https://github.com/aki-riko/Gitora/actions/runs/29878569297)
在同一 macOS 自检步骤用相对可执行路径复现失败：

```text
[Errno 2] No such file or directory: 'build_dist/main_qml.app/Contents/MacOS/Gitora'
```

根因是自检工具在切换子进程工作目录后仍传递相对可执行路径。提交 `97e9ef5` 在切换工作
目录前严格解析绝对路径，并增加相对路径回归测试。run `29879070674` 使用同一工作流输入
通过该步骤，构成同类真实失败输入的修复后验证。

## 隔离与隐私边界

- 自检创建临时 `HOME` 和 `LOCALAPPDATA`，不读取或覆盖用户的 AI 配置。
- stub 只监听动态分配的 `127.0.0.1` 端口，不访问公网，也不使用真实 API 密钥。
- 验证必须同时看到非零 `rootObjects`、AI 连接成功标志，并确认打包程序实际访问过
  回环 `/v1/models` 端点。
- 自检不发送仓库源码；回环响应只返回固定测试模型名。

## 尚未验证的事项

- 当前验证环境没有配置真实 Ollama 模型或远程 Responses 模型。
- 尚未产生真实模型的标题质量、拆分接受率、失败率和端到端延迟结论。
- macOS DMG 使用 ad-hoc 签名，未做 Apple Developer ID 签名或公证。
- 本次只完成构建与 artifact 验证，未创建 `v1.3.0` tag，也未创建 GitHub Release。
