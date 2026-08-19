# 框架与生成项目验证契约

[English](../en/TESTING.md) | 简体中文

本文件是所有框架和生成模板变更的强制回归契约。一次聚焦的 `pytest` 只能作为中间检查，不能替代完整矩阵。

## 必须保持的生命周期语义

- 有限 Spider 只有在 `start()` 生产者结束，并且该 Engine 拥有的所有请求、回调和 WebSocket 监听都到达终态后才算完成。
- `start_request_limit = None` 的 Redis、RabbitMQ 或 Kafka Spider 是持续消费者。Broker 暂时为空不代表完成；它必须保持订阅，直到 Crawler 关闭或收到其他显式停止事件。
- 正数 `start_request_limit` 表示接收指定数量的启动请求后，标准队列入口生产者完成。这是输入事件，不是空队列启发式判断。
- `response.stop_listening()` 与 Crawler 关闭是 WebSocket 的真实结束事件。队列哨兵、延时或接收超时都不能冒充关闭事件。
- 测试超时只能作为外部安全边界并用于判定挂起失败；休眠完成或到达超时绝不是通过证据。
- 混合 `run_all_spiders` 中，有限 Engine 可以先完成，持续 Engine 仍让进程存活。除非用户显式配置全局 `settings.SCHEDULER`，每个 Spider 都保留自身 Scheduler 类型。

## 必须执行的测试层级

每次变更都必须完成：

1. Windows 与 WSL Ubuntu 上的完整框架 `pytest`。
2. Windows 与 WSL Ubuntu 上分别针对 Memory、Redis、RabbitMQ、Kafka 执行 `scrapy-cffi test single`。该命令必须通过真实的 `startproject` 和 `demo` 模板路径创建一次性项目、导入项目、启动真实 HTTP/WebSocket 服务与 Broker，并执行 `runner.py`。
3. 有限模式验证：生成项目的 `engine_task` 必须自然结束。验证器只能在 `finally` 中调用 `crawler.shutdown()` 清理，强制关闭不能把超时变成成功。
4. 持续模式验证：队列 Spider 使用 `start_request_limit = None`。种子任务和 WebSocket 流结束后，`runner.py` 仍应存活；随后由验证器发送显式控制台信号，并要求看到优雅关闭证据。
5. 修改命令路由或模板时，直接冒烟验证 `scrapy-cffi demo`、`demo -r`、`demo -m`、`demo -k`、`demo -tls`；同时生成普通 `startproject` 项目并验证导入。
6. 对新增或实质修改的 Python 文件执行工程约定检查器，最后执行 `git diff --check`。

Windows 与 WSL 必须串行执行，因为二者可能共享 Docker daemon 和项目名称；并行矩阵会互相干扰，不能作为有效证据。

## 发布门禁命令

先安装框架及明确的验证依赖：

```bash
python -m pip install -e ".[kafka,rabbitmq,mysql,postgres,mongodb,verification]"
```

Windows PowerShell：

```powershell
pytest -q
scrapy-cffi test single --log-dir artifacts\release-verification\windows-final
```

WSL Ubuntu：

```bash
python -m pytest -q -p no:cacheprovider
scrapy-cffi test single \
  --log-dir artifacts/release-verification/wsl-ubuntu-final
```

最终门禁不能使用 `--no-interrupt`。普通阶段验证有限任务自然退出；Redis/RabbitMQ/Kafka 中断阶段验证持续监听和显式关闭。Memory 模式是有限任务，不得用测试专用开关强行保持存活。`--quick` 只适合日常开发，不能作为发布证据。

## 发布标签

只有分支 CI 和两套平台门禁全部通过后才允许打标签，格式必须是 `v<project-version>`：

```bash
git tag v0.4.2
git push origin v0.4.2
```

`release-v.0.4.2` 等格式不会匹配发布工作流。
