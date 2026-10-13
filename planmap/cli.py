"""planmap: project management for coding agents, tied to your GitHub issues.

  planmap init [--skill] [--hooks]
                               create .planmap/ (config + taxonomy) and a PLAN.md if missing;
                               --hooks prints a Claude Code SessionStart hook
  planmap add "Title" --feature ID [--depends 1,2] [--lane NAME] [--issue] [--body TEXT]
                               add a plan item, list it under a feature, optionally open an issue
  planmap build [--no-fetch]   rebuild .planmap/build/topology.json and .planmap/STATUS.md
  planmap open                 rebuild, start the local server, open the map
  planmap sprint [--no-open]   rebuild and print "<lane> next" for every lane
  planmap doctor               rebuild and list orphans, phantoms and unsorted items (exit 1 if any)
  planmap start N              assign the item's issue to you, label it status:in-progress, comment the branch
  planmap progress N "note"    add a note to the item's issue
  planmap done N --pr P        link PR P to the issue (Fixes #I) and clear status:in-progress
  planmap sync [--dry-run]     copy plan item text into issue bodies, between planmap markers
  planmap serve                run the server in the foreground
  planmap stop                 stop the background server

Common flags: --root DIR (project folder), --port N.
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__, build as B, config as C, doctor as D, github as G, sprint as S

PKG = Path(__file__).resolve().parent

STARTER_TAXONOMY = {
    "_about": "Pillars and features of this project. Each feature points at plan items, "
              "module files, GitHub issues, PRs or ideas. planmap build joins it with the plan "
              "file and GitHub.",
    "pillars": [{
        "id": "core", "title": "Core",
        "features": [{"id": "getting-started", "title": "Getting started", "items": ["1"],
                      "note": "Replace this with your first real feature."}],
    }],
}

HOOK_SNIPPET = {"hooks": {"SessionStart": [{"hooks": [{
    "type": "command", "command": "planmap sprint --short --no-fetch 2>/dev/null || true"}]}]}}

STARTER_PLAN = """# Plan

Each item is a "### N. Title" heading. Add a "Depends on: 1, 2" line when it waits on others.
Open its GitHub issue as "[item N] Title" and planmap links them.

## Track A

### 1. Set up the project map
Run `planmap init`, list the first features in .planmap/taxonomy.json, then `planmap doctor`.
"""


def server_up(port):
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/api/topology", timeout=2):
            return True
    except OSError:
        return False


def ensure_server(root, port):
    if server_up(port):
        return
    out = C.out_dir(root)
    log = open(out / "server.log", "a", encoding="utf-8")
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen([sys.executable, "-m", "planmap.server", "--root", str(root), "--port", str(port)],
                            stdout=log, stderr=log, **kw)
    (out / "server.pid").write_text(str(proc.pid), encoding="utf-8")
    for _ in range(40):
        if server_up(port):
            return
        time.sleep(0.25)
    sys.exit(f"planmap: the server did not start on port {port}; see .planmap/build/server.log")


def cmd_init(root, args):
    d = root / C.CONFIG_DIR
    d.mkdir(exist_ok=True)
    cfg_p = d / C.CONFIG_FILE
    if not cfg_p.exists():
        repo = B.detect_repo(root)
        cfg = {"repo": repo, "plan_file": "PLAN.md", "plan_ref": "origin/main",
               "taxonomy": ".planmap/taxonomy.json", "lane_prefix": "lane:", "port": C.DEFAULTS["port"]}
        cfg_p.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        print(f"wrote .planmap/config.json (repo: {repo or 'not detected, set it by hand'})")
    tax_p = d / "taxonomy.json"
    if not tax_p.exists():
        tax_p.write_text(json.dumps(STARTER_TAXONOMY, indent=2) + "\n", encoding="utf-8")
        print("wrote .planmap/taxonomy.json")
    cfg = C.load(root)
    plan_p = root / cfg["plan_file"]
    if not plan_p.exists():
        plan_p.write_text(STARTER_PLAN, encoding="utf-8")
        print(f"wrote {cfg['plan_file']}")
    gi = root / ".gitignore"
    line = ".planmap/build/"
    text = gi.read_text(encoding="utf-8") if gi.exists() else ""
    if line not in text.splitlines():
        gi.write_text(text + ("" if text.endswith("\n") or not text else "\n") + line + "\n", encoding="utf-8")
        print("added .planmap/build/ to .gitignore")
    if args.skill:
        dst = root / ".claude" / "skills" / "planmap" / "SKILL.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text((PKG / "skill" / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")
        print(f"wrote {dst.relative_to(root)}")
    if args.hooks:
        print("\nAdd this to .claude/settings.json so each Claude Code session starts with the lane status:\n")
        print(json.dumps(HOOK_SNIPPET, indent=2))
    print("next: planmap doctor")
    return 0


def next_item_number(text, item_heading):
    nums = [int(m.group(1)) for m in re.finditer(item_heading, text, re.M) if m.group(1).isdigit()]
    return max(nums, default=0) + 1


def cmd_add(root, cfg, args):
    tax_p = root / cfg["taxonomy"]
    tax = json.loads(tax_p.read_text(encoding="utf-8"))
    feats = {f["id"]: f for p in tax["pillars"] for f in p.get("features", [])}
    if args.feature not in feats:
        print(f"planmap: no feature '{args.feature}'. Features: {', '.join(feats) or '(none)'}", file=sys.stderr)
        return 2
    plan_p = root / cfg["plan_file"]
    text = plan_p.read_text(encoding="utf-8") if plan_p.exists() else "# Plan\n"
    n = next_item_number(text, cfg["item_heading"])
    block = f"\n### {n}. {args.title}\n"
    if args.depends:
        block += f"Depends on: {args.depends}\n"
    if args.body:
        block += f"{args.body}\n"
    plan_p.write_text(text.rstrip("\n") + "\n" + block, encoding="utf-8")
    feats[args.feature].setdefault("items", []).append(str(n))
    tax_p.write_text(json.dumps(tax, indent=2) + "\n", encoding="utf-8")
    print(f"added item {n} to {cfg['plan_file']} and feature '{args.feature}'")
    if args.issue:
        repo = cfg.get("repo") or B.detect_repo(root)
        cmd = ["gh", "issue", "create", "-R", repo, "--title", f"[item {n}] {args.title}",
               "--body", (args.body or "") + f"\n\nPlan item {n} in {cfg['plan_file']}."]
        if args.lane:
            label = cfg["lane_prefix"] + args.lane
            subprocess.run(["gh", "label", "create", label, "-R", repo, "--force"], capture_output=True)
            cmd += ["--label", label]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print(f"planmap: gh issue create failed: {r.stderr.strip()}", file=sys.stderr)
            return 1
        print(f"opened {r.stdout.strip()}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="planmap", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"planmap {__version__}")
    ap.add_argument("--root", help="project folder (default: nearest .planmap/ or git top level)")
    ap.add_argument("--port", type=int)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("init")
    p.add_argument("--skill", action="store_true", help="also write .claude/skills/planmap/SKILL.md")
    p.add_argument("--hooks", action="store_true", help="print a Claude Code SessionStart hook")
    p = sub.add_parser("start")
    p.add_argument("item", type=int)
    p = sub.add_parser("progress")
    p.add_argument("item", type=int)
    p.add_argument("note")
    p = sub.add_parser("done")
    p.add_argument("item", type=int)
    p.add_argument("--pr", type=int, required=True)
    p = sub.add_parser("sync")
    p.add_argument("--dry-run", action="store_true", help="show the issue body changes, write nothing")
    p.add_argument("--no-fetch", action="store_true")
    p = sub.add_parser("add")
    p.add_argument("title")
    p.add_argument("--feature", required=True)
    p.add_argument("--depends", help="item numbers, e.g. 2,4")
    p.add_argument("--body")
    p.add_argument("--lane")
    p.add_argument("--issue", action="store_true", help="open a GitHub issue titled [item N] Title")
    for name in ("build", "open", "sprint", "doctor"):
        p = sub.add_parser(name)
        p.add_argument("--no-fetch", action="store_true", help="skip git fetch")
        p.add_argument("--plan-ref", help="read the plan from this ref (HEAD, WORKTREE, ...)")
        if name == "sprint":
            p.add_argument("--no-open", action="store_true")
            p.add_argument("--json", action="store_true")
            p.add_argument("--short", action="store_true", help="one line per lane; never opens a browser")
    sub.add_parser("serve")
    sub.add_parser("stop")
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 1

    root = Path(args.root).resolve() if args.root else C.find_root()
    if args.cmd == "init":
        return cmd_init(root, args)
    if not (root / C.CONFIG_DIR / C.CONFIG_FILE).is_file():
        print(f"planmap: no .planmap/config.json under {root.name}/. Run `planmap init` first.", file=sys.stderr)
        return 2
    cfg = C.load(root)
    if getattr(args, "plan_ref", None):
        cfg["plan_ref"] = args.plan_ref
    port = args.port or cfg["port"]
    fetch = not getattr(args, "no_fetch", False)

    if args.cmd == "add":
        return cmd_add(root, cfg, args)
    try:
        if args.cmd == "start":
            return G.start(root, cfg, args.item)
        if args.cmd == "progress":
            return G.progress(root, cfg, args.item, args.note)
        if args.cmd == "done":
            return G.done(root, cfg, args.item, args.pr)
        if args.cmd == "sync":
            rc = G.sync(root, cfg, dry_run=args.dry_run)
            if not args.dry_run:
                B.write(root, cfg, fetch=fetch)
            return rc
    except RuntimeError as e:
        print(f"planmap: gh failed: {e}", file=sys.stderr)
        return 1
    if args.cmd == "stop":
        pid_f = C.out_dir(root) / "server.pid"
        try:
            os.kill(int(pid_f.read_text()), signal.SIGTERM)
            print("stopped")
        except (OSError, ValueError):
            print("no server started by planmap is running")
        pid_f.unlink(missing_ok=True)
        return 0
    if args.cmd == "serve":
        B.write(root, cfg, fetch=fetch)
        from .server import serve
        serve(root, port)
        return 0

    topo = B.write(root, cfg, fetch=fetch)
    if args.cmd == "doctor":
        tax = json.loads((root / cfg["taxonomy"]).read_text(encoding="utf-8"))
        return D.report(tax, topo)
    if args.cmd == "sprint":
        if args.json:
            print(json.dumps(S.lanes(topo), indent=1))
            return 0
        if args.short:
            S.print_short(topo)
            return 0
        S.print_lanes(topo)
        if not args.no_open:
            ensure_server(root, port)
            webbrowser.open(f"http://localhost:{port}/#sprint")
            print(f"\nmap: http://localhost:{port}/#sprint")
        return 0
    if args.cmd == "open":
        ensure_server(root, port)
        webbrowser.open(f"http://localhost:{port}/")
        print(f"planmap on http://localhost:{port}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
