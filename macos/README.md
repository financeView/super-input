# Squirrel / IMK 集成（Plan 2）

本目录把项目的 rerank HTTP 服务接到 macOS Squirrel 输入法：Squirrel 保留 librime 逐键路径，空闲 500ms 后才向 `127.0.0.1:47625` 请求重排。上游固定为 [`SQUIRREL_COMMIT`](SQUIRREL_COMMIT)，补丁只改输入控制器、增加回环 IPC 客户端和登记 Xcode 源文件；上游代码留在被 `.gitignore` 忽略的 `third_party/squirrel/`，不会复制进项目仓库。

## 在 Mac 上构建

需要 Apple Silicon Mac、Xcode 14 或更新版本、命令行工具、Git、Make、curl 和 Python 3。构建需要从 GitHub 下载锁定版本的 Squirrel、Rime 配方和预编译依赖。

```bash
./macos/build-squirrel.sh
```

成功后生成 `dist/SuperInput-Squirrel.app`。如需双击安装包：

```bash
./macos/build-squirrel.sh --pkg
```

输出的 `.pkg` 未签名、未公证，供个人内部测试。它会安装 Squirrel fork，可能替换已有的 `/Library/Input Methods/Squirrel.app`；安装前请备份原 app。构建脚本本身只生成文件，不安装、不覆盖系统中的输入法。不要把该包当作已通过 macOS 实机验证的正式发行版。

构建会把项目 schema 与 `luna-pinyin` 词典打包，并将 `superpinyin` 加入 Rime 方案列表。首次安装后，在 Squirrel 菜单选择 **SuperInput benchmark pinyin**。如刚安装过输入法，macOS 可能需要注销并重新登录后才会刷新输入法列表。

## 启动本地重排服务

在项目根目录的 Mac venv 中安装 MLX 依赖，并注册现有 LaunchAgent：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[ml]'
./deploy/install-launch-agent.sh
./scripts/smoke.sh
```

首次启动会下载模型并进行 warmup，可能需要几分钟；服务未就绪、token 不可读、请求超时或协议错误时，输入法会忽略重排并继续使用 librime 原生候选。服务端 token 默认在 `~/Library/Application Support/super-input/token`，客户端只接受权限为用户私有的普通文件；输入文本、候选和上下文只发送到固定的 loopback 地址，不写入日志。

## 已落地的行为

- 500ms 防抖；服务请求只包含当前组合串、librime 当前页候选、按 IMK client identity 隔离的已提交上下文、光标和页码快照。上下文为空时也会请求，因此新会话或切换控件后的第一段输入同样可重排。
- 回包同时校验会话、递增 request ID、焦点代数、按键串、组合串、光标、页码和候选快照；用户继续输入、移动光标、翻页、选字或切换应用后，旧回包会被取消或丢弃。
- L1 保留候选窗原顺序；空格、回车和方案选字键才映射到重排后的 librime 原索引。鼠标选择仍遵循用户看到的原生候选。
- 校验通过的 L2 文本作为候选窗首项显示；选择它时清除 Rime 组合态并提交这条文本。其他可见候选仍映射回原生 Rime 候选索引。
- HTTP 只走带 bearer token 的 `127.0.0.1`，超时 1.5 秒；客户端没有可用 token 或服务不可用时不拦截原生键盘输入。

## 验证边界

当前 Linux 执行环境无法编译 InputMethodKit / Xcode app，也没有 MLX 或 Apple Silicon。`./macos/verify-squirrel-patch.sh` 可在 Linux 上验证补丁仍可应用于锁定上游；`./macos/test-bridge-contract.sh` 可用 Swift 编译器验证 IPC JSON 编解码，缺少 `swiftc` 时会提示所需平台/工具链。真正的 Xcode 构建、服务 warmup、IMK 焦点/候选提交以及 p95 延迟仍必须在目标 Mac 实测。

Plan 1 的 MLX 质量、延迟、KV 前缀缓存和 L2 误放行门槛仍未闭合。此次按用户要求先实现 IMK 接入，但这不代表这些门槛已通过；实测前不应把它当作达到验收标准的成品日用输入法。
