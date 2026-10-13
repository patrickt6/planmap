"""Sprint lists: open work per lane, ready items first."""
from .build import TERMINAL

UNASSIGNED = "unassigned"


def lanes(topo):
    nodes = {n["id"]: n for n in topo["nodes"]}
    by_item = {n["item"]: n for n in topo["nodes"] if n.get("kind") == "item" and n.get("item")}

    def waiting_on(n):
        return [d for d in n.get("dependsOn") or [] if by_item.get(str(d), {}).get("status") not in TERMINAL]

    out = {}
    for n in topo["nodes"]:
        if n.get("kind") not in ("item", "issue", "pr") or n.get("status") in TERMINAL | {"unknown"}:
            continue
        if n.get("kind") == "pr":
            continue  # an open PR shows up through its item
        row = {"id": n["id"], "title": n["title"], "status": n["status"], "waitingOn": waiting_on(n),
               "note": nodes.get(n["parent"], {}).get("note"), "assignees": n.get("assignees") or []}
        out.setdefault(n.get("lane") or UNASSIGNED, []).append(row)

    def key(r):
        num = r["title"].split(".", 1)[0]
        return (1 if r["waitingOn"] else 0, {"in-progress": 0, "in-pr": 1}.get(r["status"], 2),
                int(num) if num.isdigit() else 10**6, r["title"])

    order = sorted(k for k in out if k != UNASSIGNED) + ([UNASSIGNED] if UNASSIGNED in out else [])
    return {k: sorted(out[k], key=key) for k in order}


def print_lanes(topo, limit=8):
    ls = lanes(topo)
    if not ls:
        print("Nothing open. Every planned item is built, done or closed.")
    for lane, rows in ls.items():
        print(f"\n{lane} next ({len(rows)} open)")
        for r in rows[:limit]:
            wait = f"  [waiting on {', '.join(map(str, r['waitingOn']))}]" if r["waitingOn"] else ""
            print(f"  - {r['title']} ({r['status']}){wait}")
            if r["note"]:
                print(f"      note: {r['note']}")
        if len(rows) > limit:
            print(f"  ... and {len(rows) - limit} more")


def print_short(topo):
    """One line per lane, for a SessionStart hook."""
    ls = lanes(topo)
    if not ls:
        print("planmap: nothing open")
    for lane, rows in ls.items():
        ready = [r for r in rows if not r["waitingOn"]]
        nxt = ready[0]["title"] if ready else "nothing ready"
        print(f"planmap {lane}: next {nxt} ({len(rows)} open, {len(rows) - len(ready)} blocked)")
    print("planmap: details in .planmap/STATUS.md")


def status_md(topo, recent=10):
    """The Markdown mirror written to .planmap/STATUS.md."""
    ls = lanes(topo)
    rows = [r for rs in ls.values() for r in rs]
    out = ["# Project status", "",
           "Written by `planmap build`. Do not edit by hand. Agents read this at the start of a session.", ""]
    out += ["## Next in each lane", ""]
    for lane, rs in ls.items():
        ready = [r for r in rs if not r["waitingOn"] and r["status"] not in ("in-progress", "in-pr")]
        out.append(f"- **{lane}**: " + ("; ".join(r["title"] for r in ready[:3]) if ready else "nothing ready"))
    if not ls:
        out.append("Nothing open.")
    out += ["", "## In progress", ""]
    prog = [r for r in rows if r["status"] in ("in-progress", "in-pr")]
    out += [f"- {r['title']} ({r['status']}, {', '.join('@' + a for a in r['assignees']) or 'unassigned'})"
            for r in prog] or ["None."]
    out += ["", "## Blocked", ""]
    out += [f"- {r['title']}: waiting on item {', '.join(map(str, r['waitingOn']))}"
            for r in rows if r["waitingOn"]] or ["None."]
    built = [n for n in topo["nodes"] if n.get("kind") == "item" and n.get("status") in ("built", "done")]
    built.sort(key=lambda n: int(n["item"]) if str(n.get("item", "")).isdigit() else 0, reverse=True)
    out += ["", "## Recently built (highest item numbers first)", ""]
    out += [f"- {n['title']} ({n['status']})" for n in built[:recent]] or ["None yet."]
    return "\n".join(out) + "\n"
