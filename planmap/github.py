"""Write side: update GitHub issues from the plan. Runs only when a command asks for it.

Every call goes through gh(), so tests can replace it and nothing reaches GitHub.
"""
import difflib
import json
import subprocess
import sys

from . import build as B

IN_PROGRESS = "status:in-progress"
MARK_START = "<!-- planmap:start -->"
MARK_END = "<!-- planmap:end -->"


def gh(*args):
    """Run gh and return stdout. Raises RuntimeError with gh's message on failure."""
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"gh is not installed ({e})")
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or f"gh {args[0]} failed")
    return r.stdout


def current_branch(root):
    try:
        return B.git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def repo_of(root, cfg):
    return cfg.get("repo") or B.detect_repo(root)


def issue_for_item(root, cfg, n):
    """The issue number linked to plan item n, or None."""
    data = B.load_github(root, cfg)
    if not data:
        return None
    for i in data[0]:
        if str(n) in B.item_numbers_in_title(i["title"], cfg["item_tag"]):
            return i["number"]
    return None


def _need_issue(root, cfg, n):
    i = issue_for_item(root, cfg, n)
    if i is None:
        print(f"planmap: no issue titled [item {n}] found. Open one with `planmap add ... --issue`.",
              file=sys.stderr)
    return i


def start(root, cfg, n):
    i = _need_issue(root, cfg, n)
    if i is None:
        return 1
    repo, branch = repo_of(root, cfg), current_branch(root)
    gh("label", "create", IN_PROGRESS, "-R", repo, "--force", "--color", "FBCA04")
    gh("issue", "edit", str(i), "-R", repo, "--add-assignee", "@me", "--add-label", IN_PROGRESS)
    gh("issue", "comment", str(i), "-R", repo,
       "--body", f"Started plan item {n}" + (f" on branch `{branch}`." if branch else "."))
    print(f"item {n}: issue #{i} assigned to you and marked in progress")
    return 0


def progress(root, cfg, n, note):
    i = _need_issue(root, cfg, n)
    if i is None:
        return 1
    gh("issue", "comment", str(i), "-R", repo_of(root, cfg), "--body", note)
    print(f"item {n}: note added to issue #{i}")
    return 0


def done(root, cfg, n, pr):
    i = _need_issue(root, cfg, n)
    if i is None:
        return 1
    repo = repo_of(root, cfg)
    body = json.loads(gh("pr", "view", str(pr), "-R", repo, "--json", "body"))["body"] or ""
    if f"#{i}" not in body:
        gh("pr", "edit", str(pr), "-R", repo, "--body", (body.rstrip() + f"\n\nFixes #{i}").lstrip())
    gh("issue", "comment", str(i), "-R", repo, "--body", f"Plan item {n} is done in PR #{pr}. Merging it closes this issue.")
    gh("issue", "edit", str(i), "-R", repo, "--remove-label", IN_PROGRESS)
    print(f"item {n}: issue #{i} linked to PR #{pr}; it closes when the PR merges")
    return 0


def plan_block(n, item, plan_file):
    lines = [MARK_START, f"**Plan item {n}** ({plan_file})", "", item["body"] or "(no description in the plan)"]
    if item.get("depends"):
        lines += ["", f"Depends on: {item['depends']}"]
    return "\n".join(lines + [MARK_END])


def merge_body(body, block):
    """Replace the text between the markers. Text outside them is kept as written."""
    body = body or ""
    s, e = body.find(MARK_START), body.find(MARK_END)
    if s != -1 and e > s:
        return body[:s] + block + body[e + len(MARK_END):]
    return (body.rstrip() + "\n\n" + block).lstrip() if body.strip() else block


def sync(root, cfg, dry_run=False):
    """Push plan item text into the linked issue bodies. Issue state, labels and assignees
    are pulled by `planmap build`, which sync runs after it, so STATUS.md shows them."""
    _, items = B.load_plan(root, cfg)
    data = B.load_github(root, cfg)
    if not data:
        print("planmap: GitHub is not available, nothing to sync", file=sys.stderr)
        return 1
    repo, changed = repo_of(root, cfg), 0
    for iss in data[0]:
        if iss["state"] != "OPEN":
            continue
        for n in B.item_numbers_in_title(iss["title"], cfg["item_tag"]):
            if n not in items:
                continue
            old = json.loads(gh("issue", "view", str(iss["number"]), "-R", repo, "--json", "body"))["body"] or ""
            new = merge_body(old, plan_block(n, items[n], cfg["plan_file"]))
            if new == old:
                continue
            changed += 1
            if dry_run:
                print(f"--- issue #{iss['number']} (item {n})")
                sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), (new + "\n").splitlines(True),
                                                           "github", "plan", n=1))
                print()
            else:
                gh("issue", "edit", str(iss["number"]), "-R", repo, "--body", new)
                print(f"updated issue #{iss['number']} from plan item {n}")
    print(f"{changed} issue(s) {'would change' if dry_run else 'updated'}")
    return 0
