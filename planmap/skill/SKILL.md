---
name: planmap
description: Keep the project plan and its GitHub issues current. Use at the start of every session, when you plan, spec or start a feature, at each milestone, when you open a PR for planned work, and before you finish.
---

# planmap

This repo keeps its plan in `.planmap/` and ties every plan item to a GitHub issue. You keep both current. It joins three things:

- the plan file (see `plan_file` in `.planmap/config.json`, usually `PLAN.md`). Each item is a `### N. Title` heading, with an optional `Depends on: 1, 2` line.
- `.planmap/taxonomy.json`: pillars, then features. Each feature lists its `items`, `modules` (file paths), `issues`, `prs` and `ideas`.
- GitHub issues and PRs, read with `gh`. An issue or PR titled `[item N] ...` links to plan item N without any other edit. A `lane:<name>` label puts it in that lane.

Install the CLI if `planmap --version` fails:

    pipx install git+https://github.com/patrickt6/planmap

## Start of a session

Read `.planmap/STATUS.md`. It lists the next items in each lane, what is in progress and by whom, what is blocked and why, and what was built recently. Pick the first ready item in your lane that nobody is on. If the file looks stale, run `planmap build` first.

## The work loop

Always do these, in order. Each one updates the item's GitHub issue through `gh`:

1. `planmap start N` before you write code for item N. It assigns the issue to you, labels it `status:in-progress` and comments the branch name.
2. `planmap progress N "what changed"` at each milestone (a passing test suite, a design choice, a blocker).
3. `planmap done N --pr P` when you open the PR. It adds `Fixes #<issue>` to the PR and clears the in-progress label. The merge closes the issue.
4. `planmap doctor` before you finish (see below).

Run `planmap sync --dry-run` after you edit plan item text. If the diff looks right, run `planmap sync`. It only rewrites the part of each issue body between the planmap markers.

## When you spec or start new work

1. Choose the feature it belongs to. Look in `.planmap/taxonomy.json`. If no feature fits, add one under the right pillar first, with an `id`, a `title` and an empty `items` list.
2. Add the item and open its issue in one command:

       planmap add "Short title" --feature <feature-id> --depends 2,4 --lane <lane> --issue --body "One or two lines of scope."

   This appends `### N. Short title` to the plan, adds N to the feature's `items`, and opens the issue `[item N] Short title` with the label `lane:<lane>`. Leave out `--issue` only when the user says not to open one.
3. Name the branch and the PR so they link too: put `[item N]` in the PR title.
4. When the work adds files that carry the feature, add their paths to the feature's `modules`.

## Before you finish

Run `planmap doctor`. It must print `clean`. Fix what it reports:

- ORPHAN: a feature with nothing behind it. Add items, modules or ideas, or remove the feature.
- PHANTOM: an item, issue, PR or file that does not exist. Fix the number or the path.
- UNSORTED: a plan item that no feature lists. Add its number to the right feature's `items`.

When an item ships, you can mark its plan heading `(shipped, PR #N)`. A merged `[item N]` PR already marks it built.

Commit plan, taxonomy and `.planmap/STATUS.md` changes with the code they describe. Never commit `.planmap/build/`.
