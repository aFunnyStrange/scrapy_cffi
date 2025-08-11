import argparse
from . import startproject, genspider, demo

def main():
    parser = argparse.ArgumentParser(prog="scrapy_cffi", description="scrapy_cffi CLI tool")
    subparsers = parser.add_subparsers(dest="command")

    # startproject
    sp = subparsers.add_parser("startproject", help="Create a new project")
    sp.add_argument("name", help="Project name")

    # genspider
    gp = subparsers.add_parser("genspider", help="Generate a new spider")
    gp.add_argument("-r", "--redis", action="store_true", help="Use RedisSpider")
    gp.add_argument("name", help="Spider name")
    gp.add_argument("domain", help="Target domain")

    # demo project
    demo_p = subparsers.add_parser("demo", help="Create a demo project")
    demo_p.add_argument("-r", "--redis", action="store_true", help="Use RedisSpider")

    # export
    # ep = subparsers.add_parser("export", help="Export files")
    # ep.add_argument("name", help="Filename")

    args = parser.parse_args()

    if args.command == "startproject":
        startproject.run(args.name)
    elif args.command == "genspider":
        genspider.run(args.name, args.domain, args.redis)
    # elif args.command == "export":
    #     export.run(args.name)
    elif args.command == "demo":
        result = startproject.run("demo", is_demo=True)
        if result is not None:
            return
        demo.run(args.redis)
    else:
        print(f"Unknown command: {args.command}")
        parser.print_help()
