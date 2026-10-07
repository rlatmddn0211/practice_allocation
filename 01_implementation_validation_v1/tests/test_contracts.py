"""Small regression checks for mistakes that would invalidate comparisons."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from practice_allocation.core import ALLOCATIONS, AllocationSchedule, derived_seed, fingerprint, write_json
from practice_allocation.environment import PolicySpaces
from practice_allocation.learning import AuditedReplayBuffer


class AllocationContracts(unittest.TestCase):
    def test_exact_40k_budgets_and_mid_block_resume(self):
        for candidate, counts in ALLOCATIONS.items():
            schedule = AllocationSchedule(candidate, 17)
            tasks = [schedule.next_task() for _ in range(80)]
            self.assertEqual(np.bincount(tasks, minlength=4).tolist(), (np.array(counts) * 10).tolist())
            original = AllocationSchedule(candidate, 18)
            [original.next_task() for _ in range(11)]
            restored = AllocationSchedule.from_state(original.state())
            self.assertEqual([original.next_task() for _ in range(23)], [restored.next_task() for _ in range(23)])

    def test_per_task_reset_stream_does_not_depend_on_candidate(self):
        # Candidate is deliberately absent: visit k of task i pairs across branches.
        common = [derived_seed(123, 20, task, visit) for task in range(4) for visit in range(50)]
        independent = [derived_seed(124, 20, task, visit) for task in range(4) for visit in range(50)]
        self.assertEqual(len(set(common)), len(common))
        self.assertFalse(set(common) & set(independent))


class ReplayContracts(unittest.TestCase):
    def make_replay(self, capacity):
        return AuditedReplayBuffer(capacity, PolicySpaces.observation_space, PolicySpaces.action_space,
                                   device="cpu", n_envs=1, handle_timeout_termination=True)

    def add(self, replay, step, *, done=False, timeout=False):
        obs = np.zeros((1, 43), dtype=np.float32)
        obs[0, 0] = step
        obs[0, -4 + step % 4] = 1
        replay.add(obs, obs + 0.01, np.zeros((1, 4), np.float32), np.array([float(step)]),
                   np.array([done]), [{"TimeLimit.truncated": timeout}])

    def test_timeout_bootstraps_but_true_terminal_does_not(self):
        replay = self.make_replay(8)
        self.add(replay, 1, done=True, timeout=True)
        self.add(replay, 2, done=True, timeout=False)
        self.add(replay, 3)
        samples = replay._get_samples(np.array([0, 1, 2]))
        self.assertEqual(samples.dones.cpu().numpy().reshape(-1).tolist(), [0.0, 1.0, 0.0])

    def test_uniform_valid_sampling_and_ring_buffer_birth_steps(self):
        replay = self.make_replay(8)
        for step in range(1, 13):
            self.add(replay, step)
        replay.branch_start_step = 8
        state = np.random.get_state()
        try:
            np.random.seed(901)
            values = replay.sample(80000).observations[:, 0].cpu().numpy().astype(int)
        finally:
            np.random.set_state(state)
        self.assertEqual(set(values), set(range(5, 13)))
        counts = np.bincount(values, minlength=13)[5:13]
        self.assertTrue(np.all(np.abs(counts - 10000) < 500), counts)
        self.assertAlmostEqual(replay.last_new_fraction, 0.5, delta=0.02)
        self.assertEqual(replay.pos, 4)
        self.assertTrue(replay.full)


class ArtifactContracts(unittest.TestCase):
    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            write_json(path, {"first": True})
            with self.assertRaises(FileExistsError):
                write_json(path, {"second": True})
            self.assertIn('"first"', path.read_text())

    def test_fingerprint_compares_values_not_array_addresses(self):
        state = {"x": np.arange(8, dtype=np.float32), "counter": 4}
        self.assertEqual(fingerprint(state), fingerprint({"counter": 4, "x": state["x"].copy()}))
        state["x"][0] += 1
        self.assertNotEqual(fingerprint(state), fingerprint({"counter": 4, "x": np.arange(8, dtype=np.float32)}))


if __name__ == "__main__":
    unittest.main()
