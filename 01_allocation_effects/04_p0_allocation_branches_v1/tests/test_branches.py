"""Contracts that protect the scientific comparison from implementation errors."""

import copy
import unittest

from practice_allocation.branch_analysis import comparison_rows
from practice_allocation.branch_protocol import BranchPlan, reset_plan
from practice_allocation.core import TASKS, derived_seed


class BranchContracts(unittest.TestCase):
    def test_exact_research_budget_and_separate_smoke(self):
        plan = BranchPlan()
        plan.validate()
        self.assertEqual(plan.total_steps, 400000)
        self.assertEqual(plan.branch_count, 10)
        self.assertEqual(plan.repeat_seeds, (1901, 1902))
        self.assertEqual(plan.evaluation_steps, (20000, 40000))
        self.assertEqual((1 + plan.branch_count * len(plan.evaluation_steps)) * 4 * plan.episodes_per_task, 4200)
        smoke = BranchPlan.smoke()
        smoke.validate()
        self.assertEqual(smoke.total_steps, 20000)
        self.assertEqual(smoke.bank, "diagnostic")
        with self.assertRaises(ValueError):
            BranchPlan(parent_step=400000).validate()
        with self.assertRaises(ValueError):
            BranchPlan(steps_per_branch=80000).validate()

    def test_common_reset_schedule_covers_focused_visits_and_disjoint_repeats(self):
        rows = reset_plan(BranchPlan(), {"diagnostic": [], "outcome": []})
        self.assertEqual(len(rows), 400)
        self.assertEqual(len({row["reset_seed"] for row in rows}), 400)
        for repeat in (1901, 1902):
            for task in TASKS:
                self.assertEqual([r["task_visit"] for r in rows if r["repeat_seed"] == repeat and r["task"] == task], list(range(50)))
        collision = derived_seed(1901, 20, 0, 0)
        with self.assertRaises(RuntimeError):
            reset_plan(BranchPlan(), {"outcome": [{"seed": collision}]})

    def test_relative_gain_does_not_hide_absolute_drop_and_matches_repeat(self):
        base = {"success_by_task": dict(zip(TASKS, (.4, .6, .2, .8)))}
        def branch(seed, candidate, rates):
            return {"repeat_seed": seed, "candidate": candidate,
                    "outcomes": {"40000": {"success_by_task": dict(zip(TASKS, rates))}}}
        branches = [branch(1901, "U", (.4, .4, .2, .6)),
                    branch(1901, "F_DO", (.6, .4, .2, .6)),
                    branch(1902, "U", (.8, .8, .8, .8)),
                    branch(1902, "F_DO", (.6, .4, .2, .6))]
        pristine = copy.deepcopy((base, branches))
        rows, task_rows = comparison_rows(base, branches)
        first = next(r for r in rows if r["candidate"] == "F_DO" and r["repeat_seed"] == 1901)
        second = next(r for r in rows if r["candidate"] == "F_DO" and r["repeat_seed"] == 1902)
        self.assertAlmostEqual(first["gain_pp"], -5)
        self.assertAlmostEqual(first["extra_gain_vs_uniform_pp"], 5)
        self.assertAlmostEqual(second["extra_gain_vs_uniform_pp"], -35)
        self.assertAlmostEqual(first["max_drop_pp"], 20)
        self.assertEqual(len(task_rows), 16)
        self.assertEqual((base, branches), pristine)


if __name__ == "__main__":
    unittest.main()
