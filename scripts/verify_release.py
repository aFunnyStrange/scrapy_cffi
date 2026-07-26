"""Repository entry point for the unified release verifier."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrapy_cffi.commands.verify import ALL_MODES, TOPOLOGIES, run


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify tests and all generated crawler demo transports."
    )
    parser.add_argument(
        "topology",
        nargs="?",
        default="all",
        choices=TOPOLOGIES + ("all",),
        help="Verify one topology or all topologies (default: all).",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip Docker crawls; run pytest, generation/import, and topology plans.",
    )
    parser.add_argument(
        "--no-interrupt",
        action="store_true",
        help="Skip real Ctrl+C/Ctrl+Break matrix during full verification.",
    )
    parser.add_argument(
        "--mode",
        dest="modes",
        action="append",
        choices=ALL_MODES,
        help="Limit verification to one or more modes; repeat this option.",
    )
    parser.add_argument("--log-dir", help="Directory for retained logs and summary.")
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep generated temporary projects for diagnosis.",
    )
    args = parser.parse_args()
    topologies = TOPOLOGIES if args.topology == "all" else (args.topology,)
    return run(
        quick=args.quick,
        no_interrupt=args.no_interrupt,
        modes=args.modes,
        topologies=topologies,
        log_dir=args.log_dir,
        keep_workdir=args.keep_workdir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
