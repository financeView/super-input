# super-input

macOS 拼音输入法的上下文重排核心与离线验证工具。目标是保留 librime 的逐键快速路径，只在停顿后对候选进行 L1 本地似然重排；低置信度时可升级到 L2 整句解码，并由拼音校验器拦截不合规输出。

> 仓库包含 **Plan 1：rerank 核心与离线基准**，以及 **Plan 2：Squirrel/macOS IMK 源码接入**。Plan 2 的 Xcode 构建、MLX 服务和键盘实测尚未在 Apple Silicon Mac 验证；当前执行环境只有 Linux x86_64。

## 设计与实现范围

- 设计规格：[LLM 拼音输入法设计](docs/superpowers/specs/2026-09-22-llm-pinyin-ime-design.md)
- 实施计划：[rerank 核心与基准计划](docs/superpowers/plans/2026-09-23-rerank-core-and-benchmark.md)
- 实现与验证记录：[implementation status](docs/superpowers/implementation-status.md)
- librime 构建依据：[build notes](docs/superpowers/librime-build-notes.md)
- 模糊音规则唯一来源：[`assets/superpinyin.schema.yaml`](assets/superpinyin.schema.yaml)

核心能力包含有效音节表、Rime derive 模糊音关系、完整音节 DP 切分、多音字读音、T0/T1 L2 硬校验、L1 平均 logprob 排序接口、本地/云 L2 解码、鉴权 HTTP 服务、会话超时降级策略，以及 librime 基线和模型延迟基准脚本。Squirrel 接入保留逐键 librime 路径，仅在停顿后调用 loopback rerank；L1 只改键盘选字映射，L2 作为虚拟首选候选显示。

## 环境与测试

需要 Python 3.11+。核心测试无需下载模型：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest -q
```

模糊音测试集已生成并纳入版本控制（200 条，40 个种子 × 5 档替换率）：

```bash
.venv/bin/python -m rerank.testgen
```

## librime 同 schema 基线

`baseline/build.sh` 会获取公开的 librime 源码和 luna_pinyin 词典，构建 `baseline/dump_candidates`，并安装 Rime 的 `essay.txt` 词频表及 OpenCC 简体转换数据。首次构建需 C/CMake 工具链、librime 原生依赖和 OpenCC 数据文件；脚本会探测常见安装目录，也可通过 `OPENCC_DATA_DIR` 指定。确认安装来源后，可在 macOS 或 Linux 上运行：

```bash
./baseline/build.sh
.venv/bin/python benchmark/run_baseline.py
```

工具输出的 `benchmark/datasets/baseline.json` 是本地生成物，不提交版本库。只有真实运行得到同一 schema 的 top-20，召回上限与首选基线才可作有效对照。

## MLX 模型基准（目标环境：Apple Silicon macOS）

MLX 不支持本仓库当前使用的 Linux x86_64 电脑。要在目标 Mac 完成 L1/L2、延迟曲线与 KV 缓存实测：

```bash
.venv/bin/python -m pip install -e '.[dev,ml]'
.venv/bin/python benchmark/run_bench.py
.venv/bin/python benchmark/latency_curve.py
```

模型首次运行会从模型仓库下载权重。模型基准必须与真实 librime 基线分开记录；未有目标硬件实测前，不应据本地 mock 结果决定进入 Plan 2。

## 本地服务

服务默认监听 `127.0.0.1:47625`，协议头为 `X-SuperInput-Protocol: 1`，并要求 `Authorization: Bearer <token>`。首次启动生成 0600 权限 token 文件。默认生产配置见 `~/.superinput/rerank.yaml`；BYOK 密钥从 macOS Keychain 的 `superinput-rerank` 服务项读取，不写入配置文件。

在 macOS 上创建 venv、安装依赖并下载模型后，可安装 launchd 用户代理：

```bash
./deploy/install-launch-agent.sh
./scripts/smoke.sh
```

`deploy/com.superinput.rerank.plist` 是模板；安装脚本会把仓库绝对路径写入 `~/Library/LaunchAgents`。**不要在 Linux 上运行 launchd 安装步骤**。

## Squirrel / IMK 输入法集成

macOS 构建和安装说明见 [`macos/README.md`](macos/README.md)。在 Apple Silicon Mac 上运行 `./macos/build-squirrel.sh` 构建 app，或加 `--pkg` 生成未签名的个人测试安装包。它固定 Squirrel 上游 commit 并包含 `superpinyin` schema；安装包可能替换现有 Squirrel，请先备份。源码补丁可在 Linux 用 `./macos/verify-squirrel-patch.sh` 检查；真正的 Xcode 构建、服务 warmup 和 IMK 行为必须在 Mac 实测。

## 目录

```text
src/rerank/       核心逻辑与 HTTP 服务
tests/            单元、服务和可选 librime 集成测试
assets/           Rime schema（模糊音唯一事实源）
baseline/         librime 候选转储工具与构建脚本
benchmark/        数据集生成产物与基准运行器
deploy/           macOS launchd 模板与安装脚本
macos/            Squirrel/IMK 补丁、构建入口与目标环境测试说明
scripts/          HTTP 冒烟测试
docs/             设计规格、计划和审查记录
```
