import unittest

from morphos.cosmic_kernel import CommittedProofKernel
from morphos.grid2d import Grid2D, Grid2DConfig
from morphos.sparse_scheduler import DirtyNodeGrid2D, InstrumentedDenseGrid2D


class CosmicKernelTests(unittest.TestCase):
    def _config(self, width=7, height=7):
        return Grid2DConfig(
            width=width,
            height=height,
            memory_decay=0.0,
            anchor_threshold=0.5,
            adaptive_threshold=0.35,
            anchor_coupling=0.75,
            adaptive_coupling=0.5,
            mixed_relax_threshold=0.05,
            mask="checkerboard",
            neighborhood="von_neumann",
        )

    def _stable(self, initial, config):
        model = Grid2D(initial, config=config)
        for _ in range(64):
            before = model.state_string()
            model.step(0.0)
            if model.state_string() == before:
                return model.state_string()
        self.fail("fixture did not reach a zero-stimulus fixed point")

    def _pulses(self, cells):
        first = [0.0] * cells
        first[cells // 2] = 0.9
        first[cells // 2 - 1] = -0.9
        second = [0.0] * cells
        second[cells // 2 + 7] = 0.9
        pulses = []
        for tick in range(16):
            if tick == 0:
                pulses.append(first)
            elif tick == 8:
                pulses.append(second)
            else:
                pulses.append([0.0] * cells)
        return pulses

    def test_proof_observer_does_not_change_dense_or_sparse_execution(self):
        config = self._config()
        cells = config.width * config.height
        stable = self._stable("AC" * (cells // 2) + ("A" if cells % 2 else ""), config)
        pulses = self._pulses(cells)

        raw_dense = InstrumentedDenseGrid2D(stable, config=config)
        proof_dense = CommittedProofKernel(
            stable,
            config=config,
            scheduler_cls=InstrumentedDenseGrid2D,
            proof_density=1.0,
            proof_seed=101,
        )
        raw_sparse = DirtyNodeGrid2D(stable, config=config)
        proof_sparse = CommittedProofKernel(
            stable,
            config=config,
            scheduler_cls=DirtyNodeGrid2D,
            proof_density=1.0,
            proof_seed=101,
        )

        for pulse in pulses:
            raw_dense.step(pulse)
            proof_dense.step(pulse)
            raw_sparse.step(pulse)
            proof_sparse.step(pulse)
            expected = raw_dense.state_string()
            self.assertEqual(raw_sparse.state_string(), expected)
            self.assertEqual(proof_dense.state_string(), expected)
            self.assertEqual(proof_sparse.state_string(), expected)
            self.assertEqual(raw_dense.transitions, raw_sparse.transitions)
            self.assertEqual(raw_dense.transitions, proof_dense.transitions)
            self.assertEqual(raw_dense.transitions, proof_sparse.transitions)

        self.assertEqual(raw_dense.scheduler_counters(), proof_dense.scheduler_counters())
        self.assertEqual(raw_sparse.scheduler_counters(), proof_sparse.scheduler_counters())
        self.assertTrue(proof_dense.verify_proof())
        self.assertTrue(proof_sparse.verify_proof())
        self.assertEqual(proof_dense.replay(), proof_dense.state_string())
        self.assertEqual(proof_sparse.replay(), proof_sparse.state_string())

    def test_sampling_is_scheduler_independent_for_same_transition_trace(self):
        config = self._config()
        cells = config.width * config.height
        stable = self._stable("A" * cells, config)
        pulses = self._pulses(cells)
        dense = CommittedProofKernel(
            stable,
            config=config,
            scheduler_cls=InstrumentedDenseGrid2D,
            proof_density=0.10,
            proof_seed=20260823,
        )
        sparse = CommittedProofKernel(
            stable,
            config=config,
            scheduler_cls=DirtyNodeGrid2D,
            proof_density=0.10,
            proof_seed=20260823,
        )
        for pulse in pulses:
            dense.step(pulse)
            sparse.step(pulse)
        self.assertEqual(dense.state_string(), sparse.state_string())
        self.assertEqual(dense.proof().to_jsonable(), sparse.proof().to_jsonable())
        self.assertEqual(dense.proof_metrics(), sparse.proof_metrics())

    def test_zero_sample_proof_is_valid_empty_audit(self):
        config = self._config(width=5, height=5)
        kernel = CommittedProofKernel(
            "A" * 25,
            config=config,
            scheduler_cls=InstrumentedDenseGrid2D,
            proof_density=0.0,
            proof_seed=1,
        )
        pulse = [0.0] * 25
        pulse[12] = 0.9
        kernel.step(pulse)
        self.assertEqual(kernel.proof_metrics()["audited_transitions"], 0)
        self.assertTrue(kernel.verify_proof())


if __name__ == "__main__":
    unittest.main()
