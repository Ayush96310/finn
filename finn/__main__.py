import argparse
import json
import logging
import os


def main():
    p = argparse.ArgumentParser(prog="finn")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refresh", help="pull prices + filings, enrich, raise alerts")
    r.add_argument("--days", type=int, default=2)
    rs = sub.add_parser("research", help="build the research view for one or more symbols")
    rs.add_argument("symbols", nargs="+")
    rs.add_argument("--fresh", action="store_true")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=int(os.getenv("PORT", 8000)))
    sub.add_parser("usage", help="tokens spent so far")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s", datefmt="%H:%M:%S")

    if args.cmd == "refresh":
        from .push import pipeline
        print(json.dumps(pipeline.refresh(args.days), indent=2))
    elif args.cmd == "research":
        from .pull import research
        for sym in args.symbols:
            out = research.run(sym, refresh=args.fresh)
            g = (out.get("guidance") or {}).get("tally")
            print(f"{sym}: done. guidance tally={g}")
    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run("finn.api:app", host="0.0.0.0", port=args.port)
    elif args.cmd == "usage":
        from . import llm
        print(json.dumps(llm.usage_summary(), indent=2))


if __name__ == "__main__":
    main()
