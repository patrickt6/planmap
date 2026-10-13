"""Tests for the pure parsers in planmap.build."""
import unittest

from planmap import build as B


class HeadingAnnotation(unittest.TestCase):
    def test_shipped_one_pr(self):
        a = B.parse_heading_annotation("Task model (shipped, PR #17)")
        self.assertEqual((a["state"], a["prs"]), ("shipped", [17]))

    def test_shipped_two_prs(self):
        a = B.parse_heading_annotation("Due dates (shipped, PRs #21 and #24)")
        self.assertEqual((a["state"], a["prs"]), ("shipped", [21, 24]))

    def test_trailing_remark_is_not_a_pr(self):
        a = B.parse_heading_annotation("Search (shipped, PR #30 -- fuzzy matching waits on item 9)")
        self.assertEqual(a["prs"], [30])

    def test_partly_shipped_is_not_shipped(self):
        a = B.parse_heading_annotation("Undo (partly shipped, PR #14; the rest filed as #28)")
        self.assertEqual((a["state"], a["prs"]), ("partial", [14]))

    def test_superseded_and_obsolete(self):
        self.assertEqual(B.parse_heading_annotation("Old sync (superseded by item 8, #40)")["state"], "obsolete")
        self.assertEqual(B.parse_heading_annotation("X (obsolete: replaced by Y)")["state"], "obsolete")

    def test_filed(self):
        a = B.parse_heading_annotation("Weekly digest (optional) (filed as #29)")
        self.assertEqual((a["state"], a["issue"]), ("filed", 29))

    def test_plain_parens_mean_nothing(self):
        self.assertEqual(B.parse_heading_annotation("Tags (v2)"), {})
        self.assertEqual(B.parse_heading_annotation("Merge the sync branch (sync-rewrite)"), {})


class TitleMatch(unittest.TestCase):
    def test_single_and_list(self):
        self.assertEqual(B.item_numbers_in_title("[item 14] Notifications"), ["14"])
        self.assertEqual(B.item_numbers_in_title("[items 3, 5] Sign-in and sharing"), ["3", "5"])

    def test_no_tag(self):
        self.assertEqual(B.item_numbers_in_title("Fix items 1-12 lint"), [])

    def test_custom_tag(self):
        self.assertEqual(B.item_numbers_in_title("PLAN-7: due dates", r"PLAN-(\d+)"), ["7"])


class Status(unittest.TestCase):
    def test_issue(self):
        self.assertEqual(B.issue_status({"state": "CLOSED", "stateReason": "NOT_PLANNED"}), "superseded")
        self.assertEqual(B.issue_status({"state": "CLOSED", "stateReason": "COMPLETED"}), "done")
        self.assertEqual(B.issue_status({"state": "OPEN"}), "planned")
        self.assertEqual(B.issue_status(None), "unknown")

    def test_pr(self):
        self.assertEqual(B.pr_status({"state": "MERGED"}), "built")
        self.assertEqual(B.pr_status({"state": "CLOSED"}), "closed")
        self.assertEqual(B.pr_status({"state": "OPEN"}), "in-pr")


class DependsOn(unittest.TestCase):
    def test_lists(self):
        self.assertEqual(B.parse_depends_on("1"), [1])
        self.assertEqual(B.parse_depends_on("2, 4 and 5"), [2, 4, 5])
        self.assertEqual(B.parse_depends_on("2, then whatever item 9 needs"), [2])

    def test_empty(self):
        self.assertEqual(B.parse_depends_on(None), [])
        self.assertEqual(B.parse_depends_on("the sync rewrite"), [])


PLAN = """# Plan

## Track A

### 1. First item
Body for item 1.

### 2. Second item
Depends on: 1
Body for item 2, spread
over two lines.

## Track B

### 3. Third item
Depends on: 1, 2
Must not swallow the Track B heading into item 2.
"""


class PlanParsing(unittest.TestCase):
    def setUp(self):
        self.items = B.parse_plan(PLAN, "HEAD@abc1234")

    def test_items_found(self):
        self.assertEqual(set(self.items), {"1", "2", "3"})

    def test_body_stops_at_next_heading(self):
        self.assertNotIn("Track B", self.items["2"]["body"])
        self.assertIn("spread over two lines", self.items["2"]["body"])

    def test_depends(self):
        self.assertIsNone(self.items["1"]["depends"])
        self.assertEqual(B.parse_depends_on(self.items["3"]["depends"]), [1, 2])

    def test_source_locator(self):
        self.assertEqual(self.items["1"]["source"], "HEAD@abc1234:PLAN.md:5")


if __name__ == "__main__":
    unittest.main()
