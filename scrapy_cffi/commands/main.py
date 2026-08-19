"""Compose and dispatch the scrapy-cffi command-line interface."""

import argparse
import sys
from typing import Optional

from . import banner, cinstall, demo, genspider, infra, startproject, verification


def main() -> Optional[int]:
    """Parse command-line arguments and dispatch one CLI operation."""
    parser = argparse.ArgumentParser(
        prog="scrapy-cffi",
        description="scrapy_cffi command-line tools",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    banner_p = subparsers.add_parser(
        "banner",
        help="Show the scrapy-cffi terminal banner",
    )
    banner_p.add_argument(
        "--no-color",
        action="store_true",
        help="Render plain ASCII without ANSI color sequences.",
    )

    sp = subparsers.add_parser("startproject", help="Create a new project")
    sp.add_argument("name", help="Project name")

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
        default=None,
        help=(
            "Services to manage. For single, omission starts every service "
            "currently defined in docker-compose.yml."
        ),
    )
    infra_p.add_argument(
        "--project-name",
        default=None,
        help="Optional Compose project-name prefix override.",
    )

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
        choices=verification.ALL_MODES,
        help="Limit verification to one or more modes; repeat this option.",
    )
    test_p.add_argument("--log-dir")
    test_p.add_argument("--keep-workdir", action="store_true")

    gp = subparsers.add_parser("genspider", help="Generate a new spider")
    gp.add_argument("-r", "--redis", action="store_true", help="Use RedisSpider")
    gp.add_argument(
        "-m",
        "--rabbitmq",
        action="store_true",
        help="Use RabbitMqSpider; overrides --redis",
    )
    gp.add_argument(
        "-k",
        "--kafka",
        action="store_true",
        help="Use KafkaSpider and KafkaScheduler",
    )
    gp.add_argument("name", help="Spider name")
    gp.add_argument("domain", help="Target domain")

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

    demo_p = subparsers.add_parser("demo", help="Create a demo project")
    demo_p.add_argument("-r", "--redis", action="store_true", help="Use RedisSpider")
    demo_p.add_argument(
        "-m",
        "--rabbitmq",
        action="store_true",
        help="Use RabbitMqSpider; overrides --redis",
    )
    demo_p.add_argument(
        "-k",
        "--kafka",
        action="store_true",
        help="Use KafkaSpider and KafkaScheduler",
    )
    demo_p.add_argument(
        "-tls",
        "--tls",
        action="store_true",
        help="Create a standalone TLS fingerprint inspection demo",
    )

    arguments = [
        "--help" if argument == "-help" else argument
        for argument in sys.argv[1:]
    ]
    if any(argument in {"-h", "--help"} for argument in arguments):
        banner.print_banner(force=True)

    args = parser.parse_args(arguments)

    if args.command == "banner":
        banner.print_banner(force=True, use_color=not args.no_color)
        return 0

    if args.command == "startproject":
        startproject.run(args.name)
    elif args.command == "infra":
        infra.run(
            action=args.action,
            output_dir=args.output_dir,
            topology=args.topology,
            services=args.services,
            project_name=args.project_name,
        )
    elif args.command == "test":
        topologies = (
            verification.TOPOLOGIES
            if args.topology == "all"
            else (args.topology,)
        )
        return verification.run(
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
        genspider.run(
            args.name,
            args.domain,
            args.redis,
            args.rabbitmq,
            args.kafka,
        )
    elif args.command == "demo":
        if args.tls and (args.redis or args.rabbitmq or args.kafka):
            parser.error("demo -tls cannot be combined with queue demo flags")
        result = startproject.run("demo", is_demo=True)
        if result is not None:
            return
        demo.run(args.redis, args.rabbitmq, args.kafka, use_tls=args.tls)
