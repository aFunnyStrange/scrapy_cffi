import argparse
from . import startproject, genspider, demo, geninfra, infra, cinstall, verify

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
        help="Generate the single-node stack plus all local Sentinel/cluster simulations.",
    )
    ip.add_argument(
        "--clean",
        action="store_true",
        help="Clean generated infra artifacts under --output-dir.",
    )

    infra_p = subparsers.add_parser(
        "infra",
        help="Generate and manage project-local development Docker infrastructure",
    )
    infra_p.add_argument(
        "action",
        choices=(
            "generate",
            "plan",
            "config",
            "init",
            "up",
            "status",
            "reset",
            "down",
            "destroy",
            "clean",
        ),
    )
    infra_p.add_argument(
        "--output-dir",
        default="infra",
        help="Infrastructure directory (default: infra).",
    )
    infra_p.add_argument(
        "--topology",
        choices=("single", "sentinel", "cluster"),
        default="single",
    )
    infra_p.add_argument(
        "--services",
        nargs="+",
        choices=infra.ALL_SERVICES,
        default=list(infra.ALL_SERVICES),
        help="Services to manage; defaults to the full local development stack.",
    )
    infra_p.add_argument(
        "--project-name",
        default=None,
        help="Optional Compose project-name prefix override.",
    )

    verify_p = subparsers.add_parser(
        "verify",
        help="Run the framework test suite and generated Demo verification matrix",
    )
    verify_p.add_argument(
        "--quick",
        action="store_true",
        help="Skip Docker crawls; run tests, generation/import, and topology plans.",
    )
    verify_p.add_argument(
        "--no-interrupt",
        action="store_true",
        help="Skip the real process-interrupt matrix.",
    )
    verify_p.add_argument(
        "--mode",
        dest="modes",
        action="append",
        choices=verify.ALL_MODES,
        help="Limit verification to one or more modes; repeat this option.",
    )
    verify_p.add_argument("--log-dir")
    verify_p.add_argument("--keep-workdir", action="store_true")

    test_p = subparsers.add_parser(
        "test",
        help="Run single, Sentinel, cluster, or all framework verification cases",
    )
    test_p.add_argument(
        "topology",
        nargs="?",
        default="all",
        choices=("single", "sentinel", "cluster", "all"),
    )
    test_p.add_argument(
        "--quick",
        action="store_true",
        help="Skip Docker crawls; run tests, generation/import, and topology plans.",
    )
    test_p.add_argument(
        "--no-interrupt",
        action="store_true",
        help="Skip the real process-interrupt cases.",
    )
    test_p.add_argument(
        "--mode",
        dest="modes",
        action="append",
        choices=verify.ALL_MODES,
        help="Limit verification to one or more modes; repeat this option.",
    )
    test_p.add_argument("--log-dir")
    test_p.add_argument("--keep-workdir", action="store_true")

    # genspider
    gp = subparsers.add_parser("genspider", help="Generate a new spider")
    gp.add_argument("-r", "--redis", action="store_true", help="Use RedisSpider")
    gp.add_argument("-m", "--rabbitmq", action="store_true", help="Use RabbitMqSpider, override -r/--redis")
    gp.add_argument("-k", "--kafka", action="store_true", help="Use KafkaSpider and KafkaScheduler")
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
    demo_p.add_argument("-k", "--kafka", action="store_true", help="Enable Kafka (logging or KafkaSpider transport)")

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
    elif args.command == "infra":
        infra.run(
            action=args.action,
            output_dir=args.output_dir,
            topology=args.topology,
            services=args.services,
            project_name=args.project_name,
        )
    elif args.command == "verify":
        return verify.run(
            quick=args.quick,
            no_interrupt=args.no_interrupt,
            modes=args.modes,
            topologies=verify.TOPOLOGIES,
            log_dir=args.log_dir,
            keep_workdir=args.keep_workdir,
        )
    elif args.command == "test":
        topologies = (
            verify.TOPOLOGIES
            if args.topology == "all"
            else (args.topology,)
        )
        return verify.run(
            quick=args.quick,
            no_interrupt=args.no_interrupt,
            modes=args.modes,
            topologies=topologies,
            log_dir=args.log_dir,
            keep_workdir=args.keep_workdir,
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
