"""Entrypoint selecting the runtime role of the container."""

from __future__ import annotations

import argparse
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="unitforma")
    sub = parser.add_subparsers(dest="cmd", required=True)
    api = sub.add_parser("api")
    api.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container binding
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true")
    worker = sub.add_parser("worker")
    worker.add_argument("--queues", default="default,docs,mail,periodic")
    worker.add_argument("--concurrency", type=int, default=4)
    sub.add_parser("scheduler")
    sub.add_parser("migrate")
    ba = sub.add_parser(
        "bootstrap-admin", help="flag an existing Kratos identity as platform admin"
    )
    ba.add_argument("email")
    hc = sub.add_parser("healthcheck")
    hc.add_argument("kind", choices=["live", "ready"], default="live", nargs="?")
    args = parser.parse_args(argv)

    if args.cmd == "api":
        import uvicorn

        uvicorn.run(
            "unitforma.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            proxy_headers=True,
            forwarded_allow_ips="*",
            log_config=None,
        )
        return 0
    if args.cmd == "worker":
        from unitforma.core.logging import configure_logging
        from unitforma.core.settings import get_settings
        from unitforma.jobs.app import app

        s = get_settings()
        configure_logging(s.log_level, s.log_json)
        app.run_worker(queues=args.queues.split(","), concurrency=args.concurrency)
        return 0
    if args.cmd == "scheduler":
        from unitforma.core.logging import configure_logging
        from unitforma.core.settings import get_settings
        from unitforma.jobs.app import app

        s = get_settings()
        configure_logging(s.log_level, s.log_json)
        # A worker that only runs the periodic deferrer and no queues: one replica.
        app.run_worker(queues=["__scheduler__"], concurrency=1)
        return 0
    if args.cmd == "migrate":
        rc = subprocess.call([sys.executable, "-m", "alembic", "upgrade", "head"])  # noqa: S603
        if rc != 0:
            return rc
        import asyncio

        from unitforma.jobs.schema import ensure_job_schema

        asyncio.run(ensure_job_schema())
        return 0
    if args.cmd == "bootstrap-admin":
        import asyncio

        from unitforma.identity.bootstrap import bootstrap_platform_admin

        return asyncio.run(bootstrap_platform_admin(args.email))
    if args.cmd == "healthcheck":
        from unitforma.healthcheck import main as hc_main

        sys.argv = ["healthcheck", args.kind]
        return hc_main()
    return 2


if __name__ == "__main__":
    sys.exit(main())
