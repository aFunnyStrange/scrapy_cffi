import argparse
from . import startproject, genspider, demo, geninfra, cinstall

def main():
    parser = argparse.ArgumentParser(prog="scrapy_cffi", description="scrapy_cffi CLI tool")
    subparsers = parser.add_subparsers(dest="command")

    # startproject
    sp = subparsers.add_parser("startproject", help="Create a new project")
    sp.add_argument("name", help="Project name")

    # geninfra
    ip = subparsers.add_parser("geninfra", help="Generate infra topology templates")
    ip.add_argument(
        "--output-dir",
        default="infra",
        help="Directory to write generated infra templates (default: infra).",
    )
    ip.add_argument(
        "--redis",
        choices=("single", "sentinel", "cluster"),
        default="single",
        help="Generate Redis topology templates (default: single).",
    )
    ip.add_argument(
        "--rabbitmq",
        choices=("single", "cluster"),
        default="single",
        help="Generate RabbitMQ topology templates (default: single).",
    )
    ip.add_argument(
        "--kafka",
        choices=("single", "cluster"),
        default="single",
        help="Generate Kafka topology templates (default: single).",
    )
    ip.add_argument(
        "--all",
        action="store_true",
        help="Generate complete baseline infra in single-node mode.",
    )
    ip.add_argument(
        "--clean",
        action="store_true",
        help="Clean generated infra artifacts under --output-dir.",
    )

    # genspider
    gp = subparsers.add_parser("genspider", help="Generate a new spider")
    gp.add_argument("-r", "--redis", action="store_true", help="Use RedisSpider")
    gp.add_argument("-m", "--rabbitmq", action="store_true", help="Use RabbitMqSpider, override -r/--redis")
    gp.add_argument("-k", "--kafka", action="store_true", help="Use Kafka Log")
    gp.add_argument("name", help="Spider name")
    gp.add_argument("domain", help="Target domain")

    # cinstall — system-level ctypes C extension modules
    ci = subparsers.add_parser(
        "cinstall",
        help="Install user-built C extension modules to the system cpy store",
    )
    ci.add_argument(
        "module",
        nargs="?",
        help="Module folder name (e.g. bloom). Omit with --list / --path / --init.",
    )
    ci.add_argument(
        "--source",
        help="Source module directory (default: ./cpy_resources/<module> or framework template).",
    )
    ci.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing install or scaffold.",
    )
    ci.add_argument(
        "--list",
        action="store_true",
        help="List modules installed in the system cpy store.",
    )
    ci.add_argument(
        "--path",
        action="store_true",
        help="Print system cpy root directory and exit.",
    )
    ci.add_argument(
        "--remove",
        metavar="MODULE",
        help="Remove a module from the system cpy store.",
    )
    ci.add_argument(
        "--init",
        metavar="MODULE",
        help="Scaffold ./cpy_resources/<MODULE> from framework templates for local build.",
    )
    ci.add_argument(
        "--require-binary",
        action="store_true",
        help="Fail unless build/ contains a native .dll/.so/.dylib library.",
    )

    # demo project
    demo_p = subparsers.add_parser("demo", help="Create a demo project")
    demo_p.add_argument("-r", "--redis", action="store_true", help="Use RedisSpider")
    demo_p.add_argument("-m", "--rabbitmq", action="store_true", help="Use RabbitMqSpider, override -r/--redis")
    demo_p.add_argument("-k", "--kafka", action="store_true", help="Use Kafka Log")

    # export
    # ep = subparsers.add_parser("export", help="Export files")
    # ep.add_argument("name", help="Filename")

    # server

    # connect

    args = parser.parse_args()

    if args.command == "startproject":
        startproject.run(args.name)
    elif args.command == "geninfra":
        geninfra.run(
            output_dir=args.output_dir,
            redis_topology=args.redis,
            rabbitmq_topology=args.rabbitmq,
            kafka_topology=args.kafka,
            generate_all=args.all,
            clean=args.clean,
        )
    elif args.command == "cinstall":
        cinstall.run(
            args.module,
            source=args.source,
            force=args.force,
            list_modules=args.list,
            show_path=args.path,
            remove=args.remove,
            init=args.init,
            require_binary=args.require_binary,
        )
    elif args.command == "genspider":
        genspider.run(args.name, args.domain, args.redis, args.rabbitmq, args.kafka)
    # elif args.command == "export":
    #     export.run(args.name)
    elif args.command == "demo":
        result = startproject.run("demo", is_demo=True)
        if result is not None:
            return
        demo.run(args.redis, args.rabbitmq, args.kafka)
    else:
        print(f"Unknown command: {args.command}")
        parser.print_help()
