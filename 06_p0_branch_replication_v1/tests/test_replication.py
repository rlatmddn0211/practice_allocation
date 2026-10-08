"""Protect confirmation cohorts and cross-version evaluation comparisons."""

import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

from practice_allocation.branch_protocol import BranchPlan, verify_parent
from practice_allocation.core import ROOT, TASKS, Config
from practice_allocation.replication_analysis import secondary_contrasts, write_replication_analysis
from practice_allocation.replication_protocol import verify_baseline, verify_discovery


def branch(seed, candidate, early, late):
    return {"repeat_seed": seed, "candidate": candidate,
            "outcomes": {str(h): {"success_by_task": dict(zip(TASKS, rates))}
                         for h, rates in ((20000, early), (40000, late))}}


class ReplicationContracts(unittest.TestCase):
    def test_discovery_cannot_turn_negative_replication_into_confirmation(self):
        base = {"success_by_task": dict.fromkeys(TASKS, .5)}
        plan = BranchPlan()
        old, new = [], []
        for cohort, seeds, focused in ((old, (1901, 1902), .9), (new, plan.repeat_seeds, .4)):
            for seed in seeds:
                for candidate in plan.candidates:
                    value = .5 if candidate == "U" else focused
                    cohort.append(branch(seed, candidate, (.5,) * 4, (value,) * 4))
        original = copy.deepcopy((base, old, new))
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            result = write_replication_analysis(output, base, old, new, plan, {"fixture": True})
            report = json.loads((output / "replication_summary.json").read_text(encoding="utf-8"))
            confirmation = next(r for r in report["replication"] if r["candidate"] == "F_DO")
            combined = next(r for r in report["combined_descriptive"] if r["candidate"] == "F_DO")
            self.assertEqual(confirmation["repeat_count"], 3)
            self.assertEqual(confirmation["negative_repeats"], 3)
            self.assertAlmostEqual(confirmation["mean_extra_gain_vs_uniform_pp"], -10)
            self.assertAlmostEqual(combined["mean_extra_gain_vs_uniform_pp"], 10)
            self.assertEqual(result["cohort_summary_rows"], 15)
            with self.assertRaises(RuntimeError):
                write_replication_analysis(output / "incomplete", base, old, new[:-1], plan, {})
        self.assertEqual((base, old, new), original)

    def test_secondary_dip_requires_loss_and_recovery_to_starting_level(self):
        base = {"success_by_task": dict(zip(TASKS, (.06, 1., .04, .84)))}
        candidates = [
            branch(1903, "F_DC", (.1, 1, .1, .8), (.32, 1, .1, 1)),
            branch(1903, "F_DO", (.1, 1, .1, 0), (.16, 1, .1, .84)),
            branch(1904, "F_DC", (.1, 1, .1, .8), (.18, 1, .1, 1)),
            branch(1904, "F_DO", (.1, 1, .1, 0), (.18, 1, .1, .82)),
        ]
        rows = secondary_contrasts(base, candidates, "replication")
        self.assertEqual(rows[0]["do_f_dc_minus_f_do_pp"], 16)
        self.assertTrue(rows[0]["wc_dip_then_return_to_baseline"])
        self.assertFalse(rows[1]["do_discovery_direction_repeated"])
        self.assertFalse(rows[1]["wc_dip_then_return_to_baseline"])

    def test_baseline_context_metadata_can_change_but_physical_outcomes_cannot(self):
        rows = [{"evaluation_id": "baseline", "context": "old", "policy_type": "learned_sac",
                 "bank": "outcome", "task": task, "episode_index": index, "seed": task_id * 50 + index,
                 "initial_state_hash": f"{task}_{index}", "success": index % 2, "return": index + .5, "length": 500}
                for task_id, task in enumerate(TASKS) for index in range(50)]
        base = {"success_by_task": dict.fromkeys(TASKS, .5), "success_counts": dict.fromkeys(TASKS, 25),
                "episodes_by_task": dict.fromkeys(TASKS, 50), "environment_steps": 100000, "results_hash": "old_context_hash"}
        current = dict(base, results_hash="new_context_hash")
        with tempfile.TemporaryDirectory() as folder:
            old, new = Path(folder) / "old", Path(folder) / "new"
            old.mkdir()
            new.mkdir()
            def write(directory, data):
                with (directory / "evaluation_episodes.csv").open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(data[0]))
                    writer.writeheader()
                    writer.writerows(data)
            write(old, rows)
            new_rows = [dict(r, context="replication") for r in rows]
            write(new, new_rows)
            self.assertTrue(verify_baseline(new, current, old, {"baseline": base})["passed"])
            new_rows[0]["return"] += .01
            write(new, new_rows)
            with self.assertRaises(RuntimeError):
                verify_baseline(new, current, old, {"baseline": base})

    def test_pinned_parent_discovery_and_new_reset_streams_match(self):
        config = Config.load(ROOT / "configs/learner.json")
        _, _, _, _, banks, _ = verify_parent(config)
        _, old, states, receipt, specification = verify_discovery(config, BranchPlan(), banks)
        self.assertEqual(old["branches_completed"], 10)
        self.assertEqual(len(states), 400)
        self.assertEqual(receipt["replication_reset_cases"], 600)
        self.assertTrue(receipt["disjoint_reset_seeds"])
        self.assertEqual(specification["replication_seeds"], [1903, 1904, 1905])


if __name__ == "__main__":
    unittest.main()
