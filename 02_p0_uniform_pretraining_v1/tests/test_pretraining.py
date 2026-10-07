"""Research-critical selection boundaries, ties, and fixed experiment budget."""

import unittest

from practice_allocation.core import TASKS
from practice_allocation.pretraining import Plan, selection_rules


def diagnostic(step, counts):
    return {"step": step, "success_counts": dict(zip(TASKS, counts)),
            "episodes_by_task": dict.fromkeys(TASKS, 20), "results_hash": "fixture"}


class PretrainingContracts(unittest.TestCase):
    def test_fixed_budget_and_separate_smoke(self):
        plan = Plan()
        plan.validate()
        self.assertEqual(plan.total_steps // 500, 800)
        self.assertEqual(plan.total_steps // 4, 100000)
        self.assertEqual(plan.diagnostic_steps, (0, 100000, 200000, 400000))
        self.assertEqual(plan.checkpoint_steps, (200000, 400000))
        self.assertNotEqual(Plan.smoke().stage, plan.stage)
        with self.assertRaises(ValueError):
            Plan(total_steps=200000).validate()

    def test_eligibility_needs_two_mixed_tasks(self):
        before = diagnostic(100000, [0, 0, 0, 0])
        for counts, eligible in (([0, 20, 20, 0], False), ([1, 20, 0, 20], False),
                                 ([1, 19, 0, 20], True), ([20, 19, 1, 0], True)):
            self.assertEqual(selection_rules(before, diagnostic(200000, counts))["eligible"], eligible)

    def test_unique_failure_and_progress_select_different_tasks(self):
        result = selection_rules(diagnostic(100000, [2, 7, 0, 18]), diagnostic(200000, [1, 9, 8, 18]))
        self.assertEqual(result["recommendations"], {"Uniform": "U", "Failure": "F_DO", "Progress": "F_WO"})
        self.assertEqual(result["progress_per_training_step"]["WO"], 8 / 20 / 100000)

    def test_ties_and_no_positive_progress_choose_uniform(self):
        cases = [([0, 0, 0, 0], [3, 3, 20, 20], "U", "U"),
                 ([1, 2, 3, 4], [1, 2, 3, 4], "F_DO", "U"),
                 ([5, 6, 7, 8], [4, 3, 2, 1], "F_WC", "U"),
                 ([0, 1, 2, 3], [1, 2, 3, 4], "F_DO", "U")]
        for previous, current, failure, progress in cases:
            result = selection_rules(diagnostic(200000, previous), diagnostic(400000, current))
            self.assertEqual(result["recommendations"]["Failure"], failure)
            self.assertEqual(result["recommendations"]["Progress"], progress)

    def test_selector_rejects_incomplete_evaluation(self):
        current = diagnostic(200000, [1, 2, 3, 4])
        current["episodes_by_task"]["DO"] = 19
        with self.assertRaises(ValueError):
            selection_rules(diagnostic(100000, [0, 0, 0, 0]), current)


if __name__ == "__main__":
    unittest.main()
