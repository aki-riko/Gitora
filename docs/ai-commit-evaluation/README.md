# AI 提交规划器历史回放评测

本目录保存可复跑的真实历史样本元数据和人工评价表，不保存源码差异正文。

## 当前样本基线

- 30 组样本，每组由 2 个连续 first-parent 提交组成，共覆盖 60 个互不重复提交。
- 覆盖 Python 30 组、QML 24 组、测试 26 组、文档 14 组；同一组可属于多个类别。
- 30 组合并差异合计 771451 个字符，清单只记录 SHA-256、字符数、路径和增删统计。
- `manual-evaluation.csv` 为本地与远程模型各预留 30 行，当前 60 行均为 `not_run`。
- 本机在生成基线时没有配置本地端点/模型、远程端点/模型或 API 密钥，因此没有伪造模型质量、耗时或主观评分。

## 文件

- `replay-cases.jsonl`：真实 base/target/tip、原始标题、变更路径、类别、增删量和合并差异摘要。
- `manual-evaluation.csv`：本地/远程模型的质量、耗时、失败类型和人工 1–5 分评价表。
- `tools/ai_commit_eval.py`：生成样本或在临时克隆中运行评测的命令行入口。

## 重新生成

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe tools\ai_commit_eval.py prepare `
  --repo . `
  --cases docs\ai-commit-evaluation\replay-cases.jsonl `
  --manual docs\ai-commit-evaluation\manual-evaluation.csv `
  --count 30 `
  --commits-per-case 2
```

生成过程只读取源仓库历史。实际回放会在系统临时目录创建独立克隆，把 `HEAD/index` 设为样本 base，同时让工作区保持 tip 内容，再调用 Gitora 自身的快照、协议、覆盖与补丁校验。

## 运行模型评测

本机回环 Ollama 示例：

```powershell
.\.venv\Scripts\python.exe tools\ai_commit_eval.py run `
  --repo . `
  --cases docs\ai-commit-evaluation\replay-cases.jsonl `
  --results local-evaluation-results.jsonl `
  --provider-kind local
```

远程 OpenAI 兼容 API 或非本机 Ollama 评测会发送临时回放中的源码差异，必须额外显式传入 `--allow-remote-source-upload`。没有该参数时命令会在 provider 创建及任何网络调用前拒绝执行：

```powershell
.\.venv\Scripts\python.exe tools\ai_commit_eval.py run `
  --repo . `
  --cases docs\ai-commit-evaluation\replay-cases.jsonl `
  --results remote-evaluation-results.jsonl `
  --provider-kind remote `
  --allow-remote-source-upload
```

端点、模型名、超时和密钥环境变量名均来自 Gitora AI 配置；脚本不内置 URL、模型或密钥。结果只记录协议、覆盖、重复、补丁校验、耗时和失败类型，不写入发送的源码正文。

## 评价口径

硬指标由脚本自动记录：

- 协议解析/结构校验是否成功。
- 已知变更覆盖率。
- 重复分配数。
- 隔离索引补丁校验是否成功。
- 端到端耗时、纯 provider 响应耗时和失败异常类型。

人工指标在 CSV 中填写：标题质量、分组质量、历史风格一致性、是否无需重新分组即可接受，以及说明。未真实运行或未人工阅读的单元格必须保持空白或 `not_run`，不得用模拟结果代替。
