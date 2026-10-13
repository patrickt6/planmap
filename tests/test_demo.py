"""End-to-end build of the offline demo (examples/todo-app): no network, no git fetch."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from planmap import build as B, config as C, doctor as D, sprint as S

DEMO = Path(__file__).resolve().parents[1] / "examples" / "todo-app"


class Demo(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "todo-app"
        shutil.copytree(DEMO, self.root, ignore=shutil.ignore_patterns("build"))
        self.cfg = C.load(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def topo(self):
        return B.build(self.root, self.cfg, fetch=False)

    def tax(self):
        return json.loads((self.root / self.cfg["taxonomy"]).read_text())

    def node(self, topo, nid):
        return next(n for n in topo["nodes"] if n["id"] == nid)

    def test_statuses(self):
        t = self.topo()
        self.assertEqual(self.node(t, "task-core--item-1")["status"], "built")    # heading says shipped
        self.assertEqual(self.node(t, "task-core--item-2")["status"], "in-pr")    # open PR #11
        self.assertEqual(self.node(t, "auth--item-6")["status"], "done")          # issue closed
        self.assertEqual(self.node(t, "theme--item-9")["status"], "built")        # PR #13 merged
        self.assertEqual(self.node(t, "scheduling--item-4")["blocks"], [5, 10])

    def test_lanes_come_from_labels(self):
        t = self.topo()
        self.assertEqual(t["lanes"], ["backend", "frontend"])
        lanes = S.lanes(t)
        self.assertEqual(list(lanes), ["backend", "frontend", "unassigned"])
        self.assertEqual(lanes["backend"][0]["title"], "4. Due dates")     # ready before waiting
        self.assertEqual(lanes["frontend"][0]["status"], "in-pr")

    def test_no_absolute_paths_in_sources(self):
        t = json.dumps(self.topo())
        self.assertNotIn(str(self.tmp), t)

    def test_doctor_clean(self):
        self.assertEqual(D.check(self.tax(), self.topo()), [])

    def test_doctor_flags_drift(self):
        tax = self.tax()
        feats = tax["pillars"][0]["features"]
        feats[0]["items"].append("99")                 # phantom item
        feats[0]["modules"].append("src/nope.py")      # missing module
        feats[0]["issues"] = [404]                     # phantom issue
        feats.append({"id": "empty", "title": "Empty"})  # orphan
        feats[1]["items"].remove("10")                 # unsorted
        (self.root / self.cfg["taxonomy"]).write_text(json.dumps(tax))
        kinds = sorted(p.split()[0] for p in D.check(tax, self.topo()))
        self.assertEqual(kinds, ["ORPHAN", "PHANTOM", "PHANTOM", "PHANTOM", "UNSORTED"])


if __name__ == "__main__":
    unittest.main()
