"""CPU numerical/mocked-update checks. No environment, checkpoint model, or SAC.train."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback
from types import SimpleNamespace
import uuid

os.environ["PRACTICE_SUITE"] = "B"

import numpy as np
import torch

from practice_allocation.core import TASKS, capture_rng, fingerprint, restore_rng
from retention_learning import attach_intervention, teacher_to_student_kl
from retention_memory import build_memories, MemoryIntegrityError


ROOT = Path(__file__).resolve().parent
FIXTURE_OPTIMIZER_STEPS = 0


class SquashedDiagGaussianDistribution:
    distribution = None
    gaussian_actions = None


class ToyActor(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.mu = torch.nn.Linear(8, 4)
        self.log_std = torch.nn.Linear(8, 4)
        self.action_dist = SquashedDiagGaussianDistribution()
        self.optimizer = torch.optim.SGD(self.parameters(), lr=0.04, momentum=0.2)

    def get_action_dist_params(self, observations):
        return self.mu(observations), self.log_std(observations).clamp(-20, 2), {}


class ToyReplay:
    def __init__(self, observations):
        self.observations = observations.copy()
        self.sample_calls = 0
        self.last_indices = None

    def sample(self, batch_size):
        self.sample_calls += 1
        self.last_indices = np.random.randint(0, len(self.observations), batch_size)
        return torch.as_tensor(self.observations[self.last_indices])


class ToyModel:
    """Handwritten supervised optimizer fixture, deliberately NOT an SAC subclass."""
    def __init__(self, observations):
        self.actor = ToyActor()
        self.critic = torch.nn.Linear(8, 1)
        self.critic.optimizer = torch.optim.SGD(self.critic.parameters(), lr=0.04)
        self.log_ent_coef = torch.nn.Parameter(torch.zeros(()))
        self.ent_coef_optimizer = torch.optim.SGD([self.log_ent_coef], lr=0.04)
        self.policy = SimpleNamespace(share_features_extractor=False)
        self.use_sde = False
        self.device = torch.device('cpu')
        self.replay_buffer = ToyReplay(observations)
        self.num_timesteps = 32000
        self._n_updates = 27000
        self.last_update_metrics = {}

    def _update_learning_rate(self, optimizers):
        for optimizer in optimizers:
            for group in optimizer.param_groups:
                group['lr'] = 0.04

    def train(self, gradient_steps, batch_size):
        global FIXTURE_OPTIMIZER_STEPS
        assert gradient_steps == 1
        self._update_learning_rate([self.actor.optimizer, self.critic.optimizer, self.ent_coef_optimizer])
        observations = self.replay_buffer.sample(batch_size)
        mu, log_std, _ = self.actor.get_action_dist_params(observations)
        loss = (mu - 0.25).square().mean() + 0.01 * log_std.square().mean()
        self.actor.optimizer.zero_grad()
        loss.backward()
        self.actor.optimizer.step()
        FIXTURE_OPTIMIZER_STEPS += 1
        self._n_updates += 1
        self.last_update_metrics = {'actor_loss': float(loss.detach().item())}

    def save(self, _path):
        assert '_retention_runtime' not in self.__dict__
        assert 'train' not in self.__dict__ and 'save' not in self.__dict__
        assert '_update_learning_rate' not in self.__dict__
        assert not self.actor.optimizer._optimizer_step_pre_hooks
        return {'runtime_stripped': True, 'step': self.num_timesteps}


def fixture_memory():
    size, episode_steps = 32000, 500
    births = np.arange(1, size + 1, dtype=np.int64)
    tasks = ((births - 1) // episode_steps) % len(TASKS)
    observations = np.zeros((size, 1, 8), dtype=np.float32)
    observations[:, 0, 0] = (births % 499) / 499
    observations[:, 0, 1] = (births // 500) / 64
    observations[np.arange(size), 0, 4 + tasks] = 1
    replay = SimpleNamespace(n_envs=1, optimize_memory_usage=False, total_added=size,
                             observations=observations, birth_steps=births,
                             size=lambda: size)
    engine = SimpleNamespace(at_boundary=True, config=SimpleNamespace(episode_steps=500),
                              model=SimpleNamespace(replay_buffer=replay, num_timesteps=size, _n_updates=27000))
    rows = []
    for episode in range(64):
        task = episode % 4
        within_task_bin = (episode % 16) // 4
        success = task == 1 or (task == 2 and within_task_bin % 2 == 0) or (task == 3 and within_task_bin == 0)
        rows.append({'end_step': (episode + 1) * episode_steps,
                     'task': TASKS[task], 'success': success})
    config = {'age_bins': 4, 'episodes_per_stratum': 4, 'observations_per_episode': 32,
              'memory_seed': 660202, 'zero_success_fallback': 'shared_general'}
    return engine, {'episode_rows': rows}, config


def model_state(model):
    return {'actor': model.actor.state_dict(), 'actor_optimizer': model.actor.optimizer.state_dict(),
            'critic': model.critic.state_dict(), 'critic_optimizer': model.critic.optimizer.state_dict(),
            'alpha': model.log_ent_coef, 'alpha_optimizer': model.ent_coef_optimizer.state_dict(),
            'step': model.num_timesteps, 'updates': model._n_updates,
            'sample_calls': model.replay_buffer.sample_calls,
            'sample_indices': model.replay_buffer.last_indices,
            'losses': model.last_update_metrics}


def run_updates(model, count):
    for _ in range(count):
        model.num_timesteps += 1
        model.train(gradient_steps=1, batch_size=17)


def run_direct_combined_updates(model, count, memory, teacher_mu, teacher_log_std, seed, coefficient):
    """Independent handwritten reference: one backward on (base + lambda*KL)."""
    global FIXTURE_OPTIMIZER_STEPS
    private_rng = np.random.default_rng(seed)
    for _ in range(count):
        model.num_timesteps += 1
        model._update_learning_rate([model.actor.optimizer, model.critic.optimizer, model.ent_coef_optimizer])
        observations = model.replay_buffer.sample(17)
        mu, log_std, _ = model.actor.get_action_dist_params(observations)
        base_loss = (mu - 0.25).square().mean() + 0.01 * log_std.square().mean()
        indices = private_rng.integers(0, len(memory), size=19)
        mem_mu, mem_log_std, _ = model.actor.get_action_dist_params(torch.as_tensor(memory[indices]))
        regularizer = torch.distributions.kl_divergence(
            torch.distributions.Normal(teacher_mu[indices], teacher_log_std[indices].exp()),
            torch.distributions.Normal(mem_mu, mem_log_std.exp())).sum(-1).mean()
        model.actor.optimizer.zero_grad()
        (base_loss + coefficient * regularizer).backward()
        model.actor.optimizer.step()
        FIXTURE_OPTIMIZER_STEPS += 1
        model._n_updates += 1
        model.last_update_metrics = {'actor_loss': float(base_loss.detach().item())}


def main():
    torch.set_num_threads(1)
    started, cpu_started = time.perf_counter(), time.process_time()
    run = ROOT / 'results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') +
                             '_retention_units_' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), ROOT / 'retention_learning.py', ROOT / 'retention_memory.py',
               ROOT / 'practice_allocation/core.py', ROOT / 'practice_allocation/schedules.py',
               ROOT / 'configs/suites.json']
    hashes = {}
    for source in sources:
        destination = run / 'source_snapshot' / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        hashes[str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()
    checks, failure, diagnostics = [], None, {}
    initial_rng = capture_rng()
    try:
        engine, labels, memory_config = fixture_memory()
        before_rng = fingerprint(capture_rng())
        memories = build_memories(engine, labels, 99901, memory_config)
        again = build_memories(engine, labels, 99901, memory_config)
        assert fingerprint(memories) == fingerprint(again)
        assert fingerprint(capture_rng()) == before_rng
        assert len(memories['general']['observations']) == 1408
        assert len(memories['success']['observations']) == 1408
        for row in memories['support']:
            assert row['general_transition_count'] == row['success_transition_count']
            assert row['selected_episodes_per_arm'] <= 4
            if row['shared_general_fallback']:
                c = (memories['general']['task_indices'] == TASKS.index(row['task'])) & (memories['general']['age_bin_indices'] == row['age_bin'])
                d = (memories['success']['task_indices'] == TASKS.index(row['task'])) & (memories['success']['age_bin_indices'] == row['age_bin'])
                assert np.array_equal(memories['general']['observations'][c], memories['success']['observations'][d])
                assert np.array_equal(memories['general']['birth_steps'][c], memories['success']['birth_steps'][d])
            else:
                d = (memories['success']['task_indices'] == TASKS.index(row['task'])) & (memories['success']['age_bin_indices'] == row['age_bin'])
                assert np.all(memories['success']['success_labels'][d] == 1)
        assert len(np.unique(memories['general']['replay_indices'])) == 1408
        checks.append('deterministic training-only task/age/episode matching, unique construction, explicit shared fallback, global RNG unchanged')

        invalid = copy.deepcopy(labels)
        invalid['episode_rows'].append({'end_step': 32500, 'task': TASKS[0], 'success': True})
        rejected = False
        try:
            build_memories(engine, invalid, 99901, memory_config)
        except MemoryIntegrityError:
            rejected = True
        assert rejected
        all_success = copy.deepcopy(labels)
        for row in all_success['episode_rows']:
            row['success'] = True
        assert len(build_memories(engine, all_success, 99901, memory_config)['general']['observations']) == 2048
        checks.append('future labels rejected; approved maximum is 2048 distinct observations')

        teacher_mu = torch.tensor([[0.0, 0.5]], requires_grad=False)
        teacher_log_std = torch.tensor([[0.0, -0.5]], requires_grad=False)
        student_mu = torch.tensor([[0.2, -0.3]], requires_grad=True)
        student_log_std = torch.tensor([[0.1, -0.1]], requires_grad=True)
        got = teacher_to_student_kl(teacher_mu, teacher_log_std, student_mu, student_log_std)
        expected = torch.distributions.kl_divergence(
            torch.distributions.Normal(teacher_mu, teacher_log_std.exp()),
            torch.distributions.Normal(student_mu, student_log_std.exp())).sum(-1)
        torch.testing.assert_close(got, expected)
        got.sum().backward()
        assert teacher_mu.grad is None and teacher_log_std.grad is None
        assert torch.isfinite(student_mu.grad).all() and torch.isfinite(student_log_std.grad).all()
        checks.append('teacher-to-student analytic KL matches torch distribution, finite student-only gradients')

        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(660203)
            base = ToyModel(memories['general']['observations'][:128])
        config = {**memory_config, 'batch_size': 19, 'kl_coefficient': 1.0,
                  'actor_lr_multiplier': 0.5, 'memory_sampling': 'with_replacement',
                  'telemetry_window_steps': 2, 'kl_direction': 'teacher_to_student',
                  'same_actor_step': True}
        rng = capture_rng()
        stock = copy.deepcopy(base)
        restore_rng(rng)
        run_updates(stock, 5)
        stock_rng = fingerprint(capture_rng())
        stock_state = fingerprint(model_state(stock))
        a_model = copy.deepcopy(base)
        a_engine = SimpleNamespace(model=a_model, at_boundary=True)
        restore_rng(rng)
        a = attach_intervention(a_engine, 'A', memories, config, 660204)
        run_updates(a_model, 5)
        assert fingerprint(model_state(a_model)) == stock_state
        assert fingerprint(capture_rng()) == stock_rng
        assert a._actor_step_calls == 1 and not a_model.actor.optimizer._optimizer_step_pre_hooks
        assert a.last_update_metrics['retention_weighted_actor_grad_norm'] == 0
        assert a_model.save('mock_only')['runtime_stripped']
        assert '_retention_runtime' in a_model.__dict__
        with a.suspended():
            with a.suspended():
                assert '_retention_runtime' not in a_model.__dict__
        a.close()
        assert '_retention_runtime' not in a_model.__dict__
        checks.append('A is bit-exact to handwritten stock updates; one passive hook; hooks/runtime removed for nested serialization and close')

        zero_model = copy.deepcopy(base)
        restore_rng(rng)
        zero_config = {**config, 'kl_coefficient': 0.0}
        zero = attach_intervention(SimpleNamespace(model=zero_model, at_boundary=True), 'C', memories,
                                   zero_config, 660204)
        run_updates(zero_model, 5)
        assert fingerprint(model_state(zero_model)) == stock_state
        assert fingerprint(capture_rng()) == stock_rng
        assert zero.last_update_metrics['retention_weighted_actor_grad_norm'] == 0
        assert all(not p.requires_grad and p.grad is None for p in zero.teacher.parameters())
        zero.close()
        checks.append('coefficient-zero C is bit-exact to stock, replay draws/global RNG unchanged, frozen teacher has no gradients')

        b_model = copy.deepcopy(base)
        restore_rng(rng)
        run_updates(b_model, 1)
        momentum_before_attach = fingerprint(b_model.actor.optimizer.state_dict()['state'])
        b = attach_intervention(SimpleNamespace(model=b_model, at_boundary=True), 'B', memories, config, 660204)
        assert fingerprint(b_model.actor.optimizer.state_dict()['state']) == momentum_before_attach
        with b._training_context():
            b_model._update_learning_rate([b_model.actor.optimizer, b_model.critic.optimizer, b_model.ent_coef_optimizer])
            assert fingerprint(b_model.actor.optimizer.state_dict()['state']) == momentum_before_attach
        run_updates(b_model, 3)
        assert b_model.actor.optimizer.param_groups[0]['lr'] == 0.02
        assert b_model.critic.optimizer.param_groups[0]['lr'] == 0.04
        assert b_model.ent_coef_optimizer.param_groups[0]['lr'] == 0.04
        assert '_update_learning_rate' not in b_model.__dict__
        assert len(b_model.actor.optimizer.state) == len(list(b_model.actor.parameters()))
        b.close()
        checks.append('B halves only actor LR after every schedule overwrite, retaining existing optimizer momentum state')

        reference_teacher = copy.deepcopy(base.actor)
        reference_teacher.requires_grad_(False)
        with torch.no_grad():
            teacher_mu, teacher_log_std, _ = reference_teacher.get_action_dist_params(
                torch.as_tensor(memories['general']['observations']))
        actual_model, reference_model = copy.deepcopy(base), copy.deepcopy(base)
        restore_rng(rng)
        actual = attach_intervention(SimpleNamespace(model=actual_model, at_boundary=True), 'C',
                                     memories, config, 660204)
        run_updates(actual_model, 3)
        actual_rng = fingerprint(capture_rng())
        restore_rng(rng)
        run_direct_combined_updates(reference_model, 3, memories['general']['observations'],
                                    teacher_mu, teacher_log_std, 660204, config['kl_coefficient'])
        assert fingerprint(capture_rng()) == actual_rng
        errors = []
        for left, right in zip(actual_model.actor.parameters(), reference_model.actor.parameters()):
            torch.testing.assert_close(left, right, rtol=1e-6, atol=1e-8)
            errors.append(float((left - right).abs().max().item()))
        assert actual_model.replay_buffer.sample_calls == reference_model.replay_buffer.sample_calls == 3
        assert actual._regularizer_updates == 3 and actual._actor_step_calls == 1
        diagnostics['combined_objective_max_parameter_absolute_error'] = max(errors)
        assert actual.last_update_metrics['sac_actor_grad_norm'] > 0
        assert actual.last_update_metrics['retention_weighted_actor_grad_norm'] > 0
        assert actual.last_update_metrics['combined_actor_grad_norm'] > 0
        actual.close()
        checks.append('same-step gradient accumulation matches an independent direct combined-objective backward without changing replay/global RNG')

        c_model = copy.deepcopy(base)
        restore_rng(rng)
        c = attach_intervention(SimpleNamespace(model=c_model, at_boundary=True), 'C', memories, config, 660204)
        original_teacher_hash = c.teacher_hash
        run_updates(c_model, 3)
        assert c._regularizer_updates == 3 and c._actor_step_calls == 1
        assert c.last_update_metrics['retention_kl'] > 0
        assert c.last_update_metrics['retention_weighted_actor_grad_norm'] > 0
        assert c.teacher_hash == fingerprint(c.teacher.state_dict()) == original_teacher_hash
        assert all(not p.requires_grad and p.grad is None for p in c.teacher.parameters())
        assert c_model.replay_buffer.sample_calls == 3
        sidecar = c.state_dict()
        with c.suspended():
            resumed_model = copy.deepcopy(c_model)
        resumed = attach_intervention(SimpleNamespace(model=resumed_model, at_boundary=True), 'C',
                                      memories, config, 660204, state=sidecar)
        continued_rng = capture_rng()
        run_updates(c_model, 2)
        continued_model_state = fingerprint(model_state(c_model))
        continued_controller_state = fingerprint(c.state_dict())
        continued_rng_state = fingerprint(capture_rng())
        restore_rng(continued_rng)
        run_updates(resumed_model, 2)
        assert fingerprint(model_state(resumed_model)) == continued_model_state
        assert fingerprint(resumed.state_dict()) == continued_controller_state
        assert fingerprint(capture_rng()) == continued_rng_state
        assert resumed.teacher_hash == original_teacher_hash
        assert not c_model.actor.optimizer._optimizer_step_pre_hooks
        assert not resumed_model.actor.optimizer._optimizer_step_pre_hooks
        c.close()
        resumed.close()
        checks.append('positive KL same-step gradients, immutable original teacher, private RNG, partial-window state and split-resume bit-exactness')

    except Exception:
        failure = traceback.format_exc()
    finally:
        restore_rng(initial_rng)
        result = {'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'failed' if failure else 'passed',
                  'checks': checks, 'checks_passed': len(checks), 'failure': failure,
                  'diagnostics': diagnostics,
                  'source_hashes': hashes, 'python': sys.version, 'numpy': np.__version__,
                  'torch': torch.__version__, 'platform': platform.platform(),
                  'torch_threads': torch.get_num_threads(),
                  'seeds': {'memory': 660202, 'toy_actor': 660203, 'private_regularizer': 660204},
                  'environment_steps': 0, 'checkpoint_model_loads': 0, 'SAC_train_calls': 0,
                  'GPU_operations': 0, 'handwritten_fixture_optimizer_steps': FIXTURE_OPTIMIZER_STEPS,
                  'wall_seconds': time.perf_counter() - started, 'process_cpu_seconds': time.process_time() - cpu_started,
                  'scope': 'CPU numerical/mocked-update unit checks; not SB3/physical-environment passivity, restore, or scientific efficacy evidence'}
        with (run / 'summary.json').open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        print(json.dumps({'status': result['status'], 'checks_passed': len(checks), 'output': str(run)}))
    if failure:
        raise RuntimeError(failure)


if __name__ == '__main__':
    main()
