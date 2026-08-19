# 1. 简介

[English](../../en/usage/0-start.md) | 简体中文

`scrapy_cffi` 提供 CLI，用于创建项目、生成 Spider、生成 Demo、管理本地基础设施和执行发行验证。0.1.4 及以前命令名为 `scrapy_cffi`，之后为 `scrapy-cffi`。

# 1.1 安装

```bash
pip install scrapy_cffi

# 可选 Rust Protobuf 加速，自动回退到 Python 实现
pip install "scrapy_cffi[protobuf]"
```

安装最新源码：

```bash
python -m pip install "scrapy_cffi @ git+https://github.com/aFunnyStrange/scrapy_cffi.git"
```

开发安装：

```bash
git clone https://github.com/aFunnyStrange/scrapy_cffi.git
cd scrapy_cffi
pip install -e .
```

## CLI 字符横幅

在交互式终端中查看根帮助时，会显示彩色的 `SCRAPY-CFFI` 字符横幅；
重定向帮助输出时会自动使用便于复制的纯 ASCII 版本。也可以单独预览：

```bash
scrapy-cffi banner
scrapy-cffi banner --no-color
```

CLI 同时支持 `-h`、`--help` 和 `-help`。设置标准环境变量 `NO_COLOR`
可关闭 ANSI 颜色。

# 2. `startproject`

```bash
scrapy-cffi startproject <project_name>
```

该命令创建干净的应用目录。Bloom 加速通过 `scrapy_cffi[bloom]` 安装，不再生成项目内 C 二进制；自定义 ctypes 资源仍可使用 `cinstall`，详见 [CPython 扩展](12-cpython.md)。

# 3. `genspider`

先进入生成项目：

```bash
cd <project_name>
scrapy-cffi genspider <spider_name> <domain>
scrapy-cffi genspider -r <spider_name> <domain>  # RedisSpider
scrapy-cffi genspider -m <spider_name> <domain>  # RabbitmqSpider
```

RabbitMQ 模式默认仍可使用 Redis 去重。

# 4. `demo` 与验证

```bash
scrapy-cffi demo       # Memory Spider
scrapy-cffi demo -r    # RedisSpider
scrapy-cffi demo -m    # RabbitmqSpider
scrapy-cffi demo -k    # KafkaSpider
scrapy-cffi demo -tls  # TLS Profile 检查
```

TLS Demo 为每个请求显式设置 `impersonate`，并生成 `profiles/README.md` 与 `scrapy_cffi_profiles.toml` 示例。

框架开发统一从以下入口验证：

```bash
scrapy-cffi test single
scrapy-cffi test sentinel
scrapy-cffi test cluster
scrapy-cffi test all

# 不启动 Docker 的日常快速检查
scrapy-cffi test all --quick
```

完整验证器会串行生成四种 Scheduler Demo，启动对应本地 Docker 拓扑，执行真实 HTTP/WebSocket 爬取，检查非持久化清理，发送真实进程中断，执行 pytest，并把 `summary.md`、`summary.json` 和阶段日志写入 `artifacts/release-verification/<timestamp>/`。

`--mode` 可缩小矩阵，`--no-interrupt` 跳过中断阶段，`--log-dir` 选择证据目录，`--keep-workdir` 保留生成项目。Memory 只属于 `single`/`all`；TLS Demo 请求第三方诊断服务，因此不属于确定性 Docker 矩阵。

# 5. `infra`

`infra` 在项目内生成独立的本地开发 Compose 栈，与爬虫应用镜像分离：

```bash
scrapy-cffi infra generate
scrapy-cffi infra plan --topology cluster --services redis rabbitmq kafka
scrapy-cffi infra up --topology single
scrapy-cffi infra status --topology sentinel --services redis
scrapy-cffi infra reset --topology cluster --services redis rabbitmq kafka
scrapy-cffi infra down --topology cluster --services redis rabbitmq kafka
scrapy-cffi infra clean
```

生成项目通过 `scrapy_cffi.toml` 保存 Compose 前缀：

```toml
[default]
project_name = "demo"
infra_project_name = "scrapy_cffi"
```

该值只属于 Infra 命令和脚本，不参与 Crawler 运行时。Crawler 仍通过 `REDIS_INFO`、数据库配置、`RABBITMQ_INFO` 和 `KAFKA_INFO` 连接普通地址。

单机拓扑不指定 `--services` 时启动 Compose 文件中仍存在的所有服务。普通 `up/plan/status` 会补齐缺失模板但不覆盖开发者修改；显式 `infra generate` 会刷新模板，必须像其他 Scaffold 更新一样审查。

生成内容包括单机 Compose、初始化/重置/销毁脚本、Sentinel/Cluster 模拟目录以及 `production-endpoints.example.toml`。这些多端口拓扑只用于一次性开发和集成测试，绝不是生产部署模板。生产环境仅容器化 Crawler 应用，并连接真实数据库和 Broker。

# 6. `cinstall`

把用户编译的 ctypes 模块安装到每用户系统目录，使多个项目共享它们：

```bash
scrapy-cffi cinstall --init custom_native
scrapy-cffi cinstall custom_native
scrapy-cffi cinstall custom_native --source ./cpy_resources/custom_native --require-binary --force
scrapy-cffi cinstall --list
scrapy-cffi cinstall --path
scrapy-cffi cinstall --remove custom_native
```

PyPI 不携带平台相关 `.dll`/`.so`；`SCRAPY_CFFI_CPY_DIR` 可覆盖默认系统存储路径。

# 7. 与后端系统集成

`scrapy_cffi` 只负责爬取核心。Celery 等任务调度器应作为独立进程运行，由后端向选定入口传输发布轻量任务，再由对应队列 Spider 消费。参见[系统边界图](../../assets/diagrams/system-overview.svg)。

Ctrl+C 时偶尔出现 `Task was destroyed but it is pending!` 或 `Event loop is closed`，通常是 asyncio 协作取消期间的控制台警告。框架仍会清理其拥有的资源；若资源未释放，应按缺陷处理而不是忽略。
