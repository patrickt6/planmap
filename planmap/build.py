"""Build topology.json: taxonomy + plan file + git + GitHub issues and PRs.

Sources (all read-only):
- the taxonomy (pillars and features, kept by hand)
- module paths named in the taxonomy (checked against the checkout)
- the plan file (planned items, read from plan_ref)
- GitHub issues and PRs (gh, or a fixture file)

If gh is missing or not logged in, GitHub is skipped and the rest still builds.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config as C

TERMINAL = {"built", "done", "closed", "superseded"}

STATUS_NOTES = {
    "built": "module file exists, PR merged, or the plan heading says \"shipped, PR #N\"",
    "done": "GitHub issue closed as completed",
    "in-pr": "open pull request",
    "in-progress": "open issue labelled status:in-progress",
    "closed": "pull request closed without merging",
    "planned": "in the plan or an open issue",
    "idea": "proposal only",
    "missing": "module path named in the taxonomy does not exist",
    "superseded": "closed as not planned, or marked obsolete on its plan heading",
    "unknown": "number not found",
}


def log(msg):
    print(f"planmap: {msg}", file=sys.stderr)


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=True).stdout


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


# ---------------------------------------------------------------- pure parsers

def parse_plan(text, source_prefix, plan_file="PLAN.md",
               item_heading=C.DEFAULTS["item_heading"], depends_line=C.DEFAULTS["depends_line"]):
    """Parse a plan file into {item_number: {...}}.

    An item starts at a heading that matches item_heading (default "### N. Title").
    Its body runs to the next markdown heading of any level, so a "## Track" heading
    between two items ends the first item instead of being read into it."""
    head_re = re.compile(item_heading)
    dep_re = re.compile(depends_line)
    any_heading = re.compile(r"^#{1,6} ")
    items, cur = {}, None
    for lineno, line in enumerate(text.splitlines(), 1):
        m = head_re.match(line)
        if m:
            num, title = m.group(1), m.group(2).strip()
            cur = items[num] = {"title": title, "annotation": parse_heading_annotation(title),
                                "depends": None, "body": [], "line": lineno,
                                "source": f"{source_prefix}:{plan_file}:{lineno}"}
            continue
        if any_heading.match(line):
            cur = None
            continue
        if cur is None:
            continue
        d = dep_re.match(line.strip())
        if d and cur["depends"] is None:
            cur["depends"] = d.group(1).strip()
        elif line.strip():
            cur["body"].append(line.strip())
    for it in items.values():
        it["body"] = " ".join(it["body"])
    return items


HEADING_ANNOT_RE = re.compile(r"\(([^()]*)\)\s*$")


def parse_heading_annotation(title):
    """Read a status note at the end of a plan heading: "(shipped, PR #12)",
    "(shipped, PRs #12, #14)", "(partly shipped, PR #N -- rest)", "(obsolete: why)",
    "(superseded by ...)" or "(filed as #N)". Only the part before " -- " or ";"
    counts, so a trailing remark is not read as a PR. Other parentheses mean nothing."""
    m = HEADING_ANNOT_RE.search(title)
    if not m:
        return {}
    text = m.group(1).strip()
    head = re.split(r" -- |;", text, maxsplit=1)[0]
    low = head.lower()
    if low.startswith("partly shipped"):
        return {"state": "partial", "prs": [int(n) for n in re.findall(r"#(\d+)", head)], "text": text}
    if low.startswith("shipped"):
        return {"state": "shipped", "prs": [int(n) for n in re.findall(r"#(\d+)", head)], "text": text}
    if low.startswith(("obsolete", "superseded")):
        return {"state": "obsolete", "text": text}
    filed = re.match(r"filed as #(\d+)", low)
    if filed:
        return {"state": "filed", "issue": int(filed.group(1)), "text": text}
    return {}


def item_numbers_in_title(title, item_tag=C.DEFAULTS["item_tag"]):
    """Item numbers an issue or PR title names, e.g. "[item 4] Due dates" -> ["4"]."""
    m = re.search(item_tag, title, re.IGNORECASE)
    return re.findall(r"\d+", m.group(1)) if m else []


LEADING_NUM_LIST_RE = re.compile(r"^((?:\d+|and)(?:\s*,\s*|\s+and\s+|\s*;\s*)?)+")


def parse_depends_on(text):
    """Only a leading list of item numbers ("2, 4 and 5"). Prose after it is ignored:
    an undercount is honest, a miscount is not."""
    if not text:
        return []
    m = LEADING_NUM_LIST_RE.match(text.strip())
    return [int(x) for x in re.findall(r"\d+", m.group(0))] if m else []


def issue_status(issue):
    if issue is None:
        return "unknown"
    if issue["state"] == "CLOSED":
        return "superseded" if issue.get("stateReason") == "NOT_PLANNED" else "done"
    return "planned"


def pr_status(pr):
    if pr is None:
        return "unknown"
    if pr["state"] == "MERGED":
        return "built"
    if pr["state"] == "CLOSED":
        return "closed"
    return "in-pr"


# ---------------------------------------------------------------- loaders

def git(root, *args):
    return run("git", "-C", str(root), *args)


def load_plan(root, cfg):
    ref, plan_file = cfg["plan_ref"], cfg["plan_file"]
    refs = [] if ref == "WORKTREE" else [ref] + ([] if ref == "HEAD" else ["HEAD"])
    for r in refs:
        try:
            text = git(root, "show", f"{r}:{plan_file}")
            sha = git(root, "rev-parse", "--short", r).strip()
            if r != ref:
                log(f"{plan_file} not found on {ref}; using {r}")
            prefix = f"{r}@{sha}"
            break
        except (OSError, subprocess.CalledProcessError):
            continue
    else:
        p = Path(root) / plan_file
        if not p.is_file():
            log(f"no plan file at {plan_file}; the map has no items")
            return "none", {}
        if ref != "WORKTREE":
            log(f"{plan_file} is not committed on {ref} or HEAD; reading the file on disk")
        text, prefix = p.read_text(encoding="utf-8"), "worktree"
    return prefix, parse_plan(text, prefix, plan_file, cfg["item_heading"], cfg["depends_line"])


def detect_repo(root):
    try:
        return subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                              cwd=str(root), capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def load_github(root, cfg):
    """Returns (issues, prs, repo) or None if GitHub is not available."""
    if cfg.get("github_fixture"):
        data = json.loads((Path(root) / cfg["github_fixture"]).read_text(encoding="utf-8"))
        return data.get("issues", []), data.get("prs", []), cfg.get("repo") or "fixture"
    repo = cfg.get("repo") or detect_repo(root)
    if not repo:
        log("no GitHub repo found (set \"repo\" in .planmap/config.json or run `gh auth login`); "
            "issues and PRs are skipped")
        return None
    try:
        lim = str(cfg["gh_limit"])
        issues = json.loads(run("gh", "issue", "list", "-R", repo, "--state", "all", "--limit", lim,
                                "--json", "number,title,state,stateReason,url,labels,assignees"))
        prs = json.loads(run("gh", "pr", "list", "-R", repo, "--state", "all", "--limit", lim,
                             "--json", "number,title,state,isDraft,url,headRefName"))
    except (OSError, subprocess.CalledProcessError, ValueError):
        log("gh is missing or not logged in, so issues and PRs are skipped (run `gh auth login`)")
        return None
    if len(issues) >= cfg["gh_limit"] or len(prs) >= cfg["gh_limit"]:
        log(f"hit gh_limit ({cfg['gh_limit']}); raise it in .planmap/config.json")
    return issues, prs, repo


def fetch_origin(root):
    try:
        subprocess.run(["git", "-C", str(root), "fetch", "--quiet", "origin"], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        log("git fetch failed; building from local refs")


# ---------------------------------------------------------------- build

def build(root, cfg, fetch=True):
    root = Path(root)
    if fetch and cfg["plan_ref"] != "WORKTREE" and not cfg.get("github_fixture"):
        fetch_origin(root)
    tax = json.loads((root / cfg["taxonomy"]).read_text(encoding="utf-8"))
    try:
        head_sha = git(root, "rev-parse", "--short", "HEAD").strip()
    except (OSError, subprocess.CalledProcessError):
        head_sha = "worktree"
    plan_ref, items = load_plan(root, cfg)
    gh = load_github(root, cfg)
    issues_l, prs_l, repo = gh or ([], [], "")
    issues = {i["number"]: i for i in issues_l}
    prs = {p["number"]: p for p in prs_l}
    tag, prefix = cfg["item_tag"], cfg["lane_prefix"]
    item_issues, item_prs, issue_lane = {}, {}, {}
    for i in issues_l:
        for n in item_numbers_in_title(i["title"], tag):
            item_issues.setdefault(n, i["number"])
        for lab in i.get("labels", []):
            if lab["name"].startswith(prefix):
                issue_lane[i["number"]] = lab["name"][len(prefix):]
    for p in prs_l:
        for n in item_numbers_in_title(p["title"], tag):
            item_prs.setdefault(n, p["number"])

    nodes, used, by_num = [], set(), {}

    def add(node):
        nodes.append(node)
        return node["id"]

    for pillar in tax["pillars"]:
        pid = add({"id": pillar["id"], "parent": None, "level": "pillar", "title": pillar["title"],
                   "source": pillar.get("source", cfg["taxonomy"])})
        for feat in pillar.get("features", []):
            fid = add({"id": feat["id"], "parent": pid, "level": "feature", "title": feat["title"],
                       "note": feat.get("note"), "source": cfg["taxonomy"]})
            feat_issues, feat_prs = feat.get("issues", []), feat.get("prs", [])
            for path in feat.get("modules", []):
                ok = (root / path).is_file()
                add({"id": f"{fid}--module-{slug(path)}", "parent": fid, "level": "sub", "kind": "module",
                     "title": path, "status": "built" if ok else "missing",
                     "source": f"HEAD@{head_sha}:{path}" if ok else f"HEAD@{head_sha}: not found at {path}"})
            for n in feat.get("items", []):
                key = str(n)
                it = items.get(key)
                if not it:
                    add({"id": f"{fid}--item-{key}", "parent": fid, "level": "sub", "kind": "item",
                         "item": key, "title": f"item {key}", "status": "unknown",
                         "source": f"not found in {cfg['plan_file']}"})
                    continue
                used.add(key)
                annot = it["annotation"]
                issue_n, via = item_issues.get(key), "auto-linked from issue title"
                if issue_n is None and annot.get("state") == "filed" and annot["issue"] in issues:
                    issue_n, via = annot["issue"], "plan heading \"filed as #N\""
                pr_n = item_prs.get(key)
                lane = issue_lane.get(issue_n) if issue_n else None
                status = "planned"
                for p in feat_prs:
                    if pr_status(prs.get(p)) == "built":
                        status = "built"
                for q in feat_issues:
                    if issue_status(issues.get(q)) == "done" and status == "planned":
                        status = "done"
                if status == "planned" and pr_n:
                    ps = pr_status(prs.get(pr_n))
                    if ps in ("built", "in-pr"):
                        status = ps
                if status == "planned" and issue_n and issue_status(issues.get(issue_n)) in ("done", "superseded"):
                    status = issue_status(issues.get(issue_n))
                iss_open = issues.get(issue_n) if issue_n else None
                if status == "planned" and iss_open and iss_open["state"] == "OPEN" and any(
                        lab["name"] == "status:in-progress" for lab in iss_open.get("labels", [])):
                    status = "in-progress"
                if annot.get("state") == "shipped" and status in ("planned", "in-pr", "in-progress"):
                    status = "built"
                elif annot.get("state") == "obsolete" and status in ("planned", "in-pr", "in-progress"):
                    status = "superseded"
                node = {"id": f"{fid}--item-{key}", "parent": fid, "level": "sub", "kind": "item",
                        "item": key, "title": f"{key}. {it['title']}", "status": status, "lane": lane,
                        "laneSource": f"issue #{issue_n} label {prefix}{lane}" if lane else None,
                        "depends": it["depends"], "dependsOn": parse_depends_on(it["depends"]),
                        "blocks": [], "body": it["body"], "source": it["source"],
                        "assignees": [a["login"] for a in (iss_open or {}).get("assignees", [])]}
                if annot.get("state") in ("shipped", "partial", "obsolete"):
                    node["headingNote"] = {"state": annot["state"], "text": annot["text"], "prs": annot.get("prs", [])}
                if issue_n and issue_n not in feat_issues:
                    iss = issues.get(issue_n)
                    node["linkedIssue"] = {"number": issue_n, "url": iss["url"] if iss else None,
                                           "status": issue_status(iss), "source": via}
                if pr_n and pr_n not in feat_prs:
                    pr = prs.get(pr_n)
                    node["linkedPr"] = {"number": pr_n, "url": pr["url"] if pr else None,
                                        "status": pr_status(pr), "source": "auto-linked from PR title"}
                add(node)
                if key.isdigit():
                    by_num[int(key)] = node
            for n in feat_issues:
                iss = issues.get(n)
                add({"id": f"{fid}--issue-{n}", "parent": fid, "level": "sub", "kind": "issue",
                     "title": f"#{n} {iss['title'] if iss else '(not found)'}", "status": issue_status(iss),
                     "lane": issue_lane.get(n), "url": iss["url"] if iss else None,
                     "source": f"gh issue view {n} -R {repo}"})
            for n in feat_prs:
                pr = prs.get(n)
                add({"id": f"{fid}--pr-{n}", "parent": fid, "level": "sub", "kind": "pr",
                     "title": f"PR #{n} {pr['title'] if pr else '(not found)'}", "status": pr_status(pr),
                     "url": pr["url"] if pr else None, "branch": pr["headRefName"] if pr else None,
                     "source": f"gh pr view {n} -R {repo}"})
            for i, idea in enumerate(feat.get("ideas", []), 1):
                add({"id": f"{fid}--idea-{i}", "parent": fid, "level": "sub", "kind": "idea", "title": idea,
                     "status": "idea", "source": cfg["taxonomy"]})

    # Nothing is dropped: plan items no feature claims go to an "Unsorted" pillar.
    left = sorted(set(items) - used, key=lambda k: int(re.sub(r"\D", "", k) or 0))
    if left:
        uid = add({"id": "unsorted", "parent": None, "level": "pillar", "title": "Unsorted",
                   "source": "planmap build"})
        for k in left:
            it = items[k]
            add({"id": f"unsorted--item-{k}", "parent": uid, "level": "sub", "kind": "item", "item": k,
                 "title": f"{k}. {it['title']}", "dependsOn": parse_depends_on(it["depends"]), "blocks": [],
                 "status": {"shipped": "built", "obsolete": "superseded"}.get(it["annotation"].get("state"), "planned"),
                 "source": it["source"]})

    for num, node in by_num.items():
        for dep in node["dependsOn"]:
            d = by_num.get(dep)
            if d is not None and num not in d["blocks"]:
                d["blocks"].append(num)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project": tax.get("name") or (repo or root.name),
        "sources": {"head": head_sha, "plan": plan_ref, "planFile": cfg["plan_file"],
                    "github": repo if gh else "skipped"},
        "lanes": sorted(set(issue_lane.values())),
        "statusNotes": STATUS_NOTES,
        "nodes": nodes,
    }


def write(root, cfg, fetch=True):
    topo = build(root, cfg, fetch=fetch)
    out = C.out_dir(root) / "topology.json"
    out.write_text(json.dumps(topo, indent=1), encoding="utf-8")
    from .sprint import status_md
    (Path(root) / C.CONFIG_DIR / "STATUS.md").write_text(status_md(topo), encoding="utf-8")
    counts = {}
    for n in topo["nodes"]:
        counts[n["level"]] = counts.get(n["level"], 0) + 1
    unsorted = sum(1 for n in topo["nodes"] if n["parent"] == "unsorted")
    print(f"planmap: {len(topo['nodes'])} nodes {counts}, {unsorted} unsorted -> "
          f"{out.relative_to(root)}", file=sys.stderr)
    return topo
