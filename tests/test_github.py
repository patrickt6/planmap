"""Write commands with gh replaced by a fake: nothing reaches GitHub."""
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from planmap import build as B, cli, config as C, github as G, sprint as S

DEMO = Path(__file__).resolve().parents[1] / "examples" / "todo-app"


class FakeGh:
    def __init__(self, bodies=None):
        self.calls, self.bodies = [], bodies or {}

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] in (("issue", "view"), ("pr", "view")):
            return json.dumps({"body": self.bodies.get(args[2], "")})
        return ""

    def find(self, *prefix):
        return [c for c in self.calls if c[:len(prefix)] == prefix]


class WriteCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "todo-app"
        shutil.copytree(DEMO, self.root, ignore=shutil.ignore_patterns("build"))
        self.cfg = C.load(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_cli(self, *argv, fake=None):
        fake = fake or FakeGh()
        with mock.patch.object(G, "gh", fake), mock.patch.object(G, "current_branch", lambda r: "issue-6-due-dates"), \
                redirect_stdout(io.StringIO()) as out:
            rc = cli.main(["--root", str(self.root), *argv])
        return rc, fake, out.getvalue()

    def test_start_assigns_labels_and_comments(self):
        rc, gh, _ = self.run_cli("start", "4")   # item 4 is issue #6 in the fixture
        self.assertEqual(rc, 0)
        edit = gh.find("issue", "edit", "6")[0]
        self.assertIn("@me", edit)
        self.assertIn(G.IN_PROGRESS, edit)
        self.assertIn("issue-6-due-dates", " ".join(gh.find("issue", "comment", "6")[0]))

    def test_progress_comments(self):
        rc, gh, _ = self.run_cli("progress", "4", "API done")
        self.assertEqual(rc, 0)
        self.assertEqual(gh.find("issue", "comment", "6")[0][-1], "API done")

    def test_done_links_pr_and_clears_label(self):
        rc, gh, _ = self.run_cli("done", "4", "--pr", "20", fake=FakeGh({"20": "Adds due dates."}))
        self.assertEqual(rc, 0)
        self.assertTrue(gh.find("pr", "edit", "20")[0][-1].endswith("Fixes #6"))
        self.assertIn(G.IN_PROGRESS, gh.find("issue", "edit", "6")[0])

    def test_done_keeps_existing_fixes_line(self):
        _, gh, _ = self.run_cli("done", "4", "--pr", "20", fake=FakeGh({"20": "Fixes #6"}))
        self.assertEqual(gh.find("pr", "edit"), [])

    def test_unknown_item_writes_nothing(self):
        with mock.patch("sys.stderr", io.StringIO()):
            rc, gh, _ = self.run_cli("start", "99")
        self.assertEqual(rc, 1)
        self.assertEqual(gh.calls, [])

    def test_sync_dry_run_writes_nothing(self):
        rc, gh, out = self.run_cli("sync", "--dry-run", "--no-fetch")
        self.assertEqual(rc, 0)
        self.assertEqual(gh.find("issue", "edit"), [])
        self.assertIn(G.MARK_START, out)

    def test_sync_keeps_human_text(self):
        human = "Written by a person.\n\n" + G.MARK_START + "\nold\n" + G.MARK_END + "\n\nAlso theirs."
        rc, gh, _ = self.run_cli("sync", "--no-fetch", fake=FakeGh({"6": human}))
        self.assertEqual(rc, 0)
        body = next(c for c in gh.find("issue", "edit", "6"))[-1]
        self.assertTrue(body.startswith("Written by a person."))
        self.assertTrue(body.endswith("Also theirs."))
        self.assertNotIn("\nold\n", body)

    def test_merge_body_is_stable(self):
        block = G.plan_block("4", {"body": "x", "depends": None}, "PLAN.md")
        once = G.merge_body("hi", block)
        self.assertEqual(G.merge_body(once, block), once)

    def test_in_progress_label_and_status_md(self):
        data = json.loads((self.root / "github.json").read_text())
        iss = next(i for i in data["issues"] if i["number"] == 6)
        iss["labels"].append({"name": G.IN_PROGRESS})
        iss["assignees"] = [{"login": "dev"}]
        (self.root / "github.json").write_text(json.dumps(data))
        with mock.patch("sys.stderr", io.StringIO()):
            B.write(self.root, self.cfg, fetch=False)
        md = (self.root / ".planmap" / "STATUS.md").read_text()
        self.assertIn("4. Due dates (in-progress, @dev)", md)
        self.assertIn("waiting on item 4", md)

    def test_sprint_short_and_hooks(self):
        rc, _, out = self.run_cli("sprint", "--short", "--no-fetch")
        self.assertEqual(rc, 0)
        self.assertIn("planmap backend: next 4. Due dates", out)
        rc, _, out = self.run_cli("init", "--hooks")
        self.assertIn("sprint --short", out)


if __name__ == "__main__":
    unittest.main()
