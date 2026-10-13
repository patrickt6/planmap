"""Drift checks on a built topology.

ORPHAN   a feature with nothing behind it (no modules, items, issues, PRs or ideas)
PHANTOM  an issue, PR or item number in the taxonomy that does not exist,
         or a module path that is not in the checkout
UNSORTED a plan item that no feature lists

Returns a list of problem strings. Empty means clean.
"""


def check(tax, topo):
    problems = []
    gh_ok = topo.get("sources", {}).get("github") != "skipped"
    for pillar in tax["pillars"]:
        for feat in pillar.get("features", []):
            if not any(feat.get(k) for k in ("modules", "items", "issues", "prs", "ideas")):
                problems.append(f"ORPHAN   {pillar['id']}/{feat['id']} \"{feat['title']}\": "
                                "no modules, items, issues, prs or ideas")
    for n in topo["nodes"]:
        kind, title = n.get("kind"), n.get("title", "")
        if kind in ("issue", "pr") and "(not found)" in title and gh_ok:
            problems.append(f"PHANTOM  {n['id']}: {title} does not exist on GitHub")
        if kind == "item" and n.get("status") == "unknown":
            problems.append(f"PHANTOM  {n['id']}: item {n.get('item')} is not in the plan file")
        if kind == "module" and n.get("status") == "missing":
            problems.append(f"PHANTOM  {n['id']}: no file at {title}")
        if n.get("parent") == "unsorted":
            problems.append(f"UNSORTED {n['id']}: \"{title}\" is in no feature's items list")
    return problems


def report(tax, topo):
    if topo.get("sources", {}).get("github") == "skipped":
        print("planmap doctor: GitHub was skipped, so issue and PR numbers were not checked.")
    problems = check(tax, topo)
    if not problems:
        feats = sum(len(p.get("features", [])) for p in tax["pillars"])
        print(f"planmap doctor: clean. {len(tax['pillars'])} pillars, {feats} features.")
        return 0
    print(f"planmap doctor: {len(problems)} problem(s)")
    for p in problems:
        print("  " + p)
    return 1
