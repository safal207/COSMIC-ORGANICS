import unittest

from morphos.grid2d import Grid2D, Grid2DConfig
from morphos.sparse_scheduler import DirtyNodeGrid2D, InstrumentedDenseGrid2D


class SparseSchedulerControlTests(unittest.TestCase):
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

    def _assert_trace_equal(self, initial, pulses, config):
        dense = InstrumentedDenseGrid2D(initial, config=config)
        dirty = DirtyNodeGrid2D(initial, config=config)
        for pulse in pulses:
            dense.step(pulse)
            dirty.step(pulse)
            self.assertEqual(dirty.state_string(), dense.state_string())
            self.assertEqual(dirty.transitions, dense.transitions)
            self.assertEqual(dirty.tick, dense.tick)
        return dense, dirty

    def test_single_sparse_pulse_matches_dense_every_tick(self):
        config = self._config()
        cells = config.width * config.height
        pulse = [0.0] * cells
        pulse[cells // 2] = 0.9
        pulses = [pulse] + [[0.0] * cells for _ in range(11)]
        dense, dirty = self._assert_trace_equal("A" * cells, pulses, config)
        self.assertLess(dirty.node_evaluations, dense.node_evaluations)
        self.assertGreater(dirty.unchanged_node_evaluations_avoided, 0)

    def test_signed_sparse_pulses_match_dense(self):
        config = self._config()
        cells = config.width * config.height
        initial = "AC" * (cells // 2) + ("A" if cells % 2 else "")

        # Relax the reference state first; the scheduler experiment begins only
        # from a zero-stimulus fixed point as frozen by the preregistration.
        relax = Grid2D(initial, config=config)
        for _ in range(64):
            before = relax.state_string()
            relax.step(0.0)
            if relax.state_string() == before:
                break
        else:
            self.fail("test fixture did not reach a fixed point")

        stable = relax.state_string()
        first = [0.0] * cells
        first[3] = 0.9 if stable[3] != "C" else -0.9
        first[20] = 0.9 if stable[20] != "C" else -0.9
        second = [0.0] * cells
        second[11] = 0.9 if stable[11] != "C" else -0.9

        pulses = []
        for tick in range(16):
            if tick == 0:
                pulses.append(first)
            elif tick == 8:
                pulses.append(second)
            else:
                pulses.append([0.0] * cells)
        self._assert_trace_equal(stable, pulses, config)

    def test_dense_activity_is_required_negative_control(self):
        config = self._config(width=5, height=5)
        cells = config.width * config.height
        full = [0.9] * cells
        dense, dirty = self._assert_trace_equal(
            "A" * cells,
            [full, [0.0] * cells, [0.0] * cells],
            config,
        )
        self.assertEqual(dirty.node_evaluations, dense.node_evaluations)

    def test_memory_decay_nonzero_fails_closed(self):
        config = Grid2DConfig(width=5, height=5, memory_decay=0.25)
        with self.assertRaises(ValueError):
            DirtyNodeGrid2D("A" * 25, config=config)


if __name__ == "__main__":
    unittest.main()
