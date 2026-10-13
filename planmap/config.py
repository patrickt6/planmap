"""Find the project root and load .planmap/config.json."""
import json
import subprocess
from pathlib import Path

CONFIG_DIR = ".planmap"
CONFIG_FILE = "config.json"
OUT_DIR = "build"  # .planmap/build/ holds generated files; init adds it to .gitignore

DEFAULTS = {
    # "owner/name" on GitHub. Empty means: ask `gh repo view` at build time.
    "repo": "",
    # The plan file: one "### N. Title" heading per item, optional "Depends on: 1, 2" line.
    "plan_file": "PLAN.md",
    # Git ref the plan is read from. "WORKTREE" reads the file on disk.
    # If the ref does not exist yet, the build falls back to HEAD, then to the worktree.
    "plan_ref": "origin/main",
    "taxonomy": ".planmap/taxonomy.json",
    # Heading that starts a plan item. Group 1 is the item number, group 2 the title.
    "item_heading": r"^#{2,4} (\d+)\. (.+)$",
    "depends_line": r"^Depends on:\s*(.*)$",
    # Issue and PR titles that match link to plan items. Group 1 holds the numbers.
    "item_tag": r"\[items?\s+([\d,\s]+)\]",
    # Issue labels that start with this prefix put the item in that lane.
    "lane_prefix": "lane:",
    "port": 7878,
    # Optional: a JSON file with {"issues": [...], "prs": [...]} used instead of gh.
    # The demo uses this so it builds offline.
    "github_fixture": "",
    "gh_limit": 2000,
}


def find_root(start=None):
    """The nearest folder with .planmap/config.json, else the git top level, else cwd."""
    here = Path(start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / CONFIG_DIR / CONFIG_FILE).is_file():
            return d
    try:
        top = subprocess.run(["git", "-C", str(here), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True).stdout.strip()
        if top:
            return Path(top)
    except (OSError, subprocess.CalledProcessError):
        pass
    return here


def load(root):
    cfg = dict(DEFAULTS)
    p = Path(root) / CONFIG_DIR / CONFIG_FILE
    if p.is_file():
        user = json.loads(p.read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in user.items() if not k.startswith("_")})
    return cfg


def out_dir(root):
    d = Path(root) / CONFIG_DIR / OUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d
