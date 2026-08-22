import unittest

from morphos.bardo_frontier import BardoFrontierGrid2D, FrontierRelation
from morphos.grid2d import Grid2DConfig
from morphos.sparse_scheduler import DirtyNodeGrid2D, InstrumentedDenseGrid2D


class BardoFrontierCandidateTests(unittest.TestCase):
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

    def test_candidate_matches_dense_and_dirty_every_tick(self):
        config = self._config()
        cells = config.width * config.height
        dense = InstrumentedDenseGrid2D("A" * cells, config=config)
        dirty = DirtyNodeGrid2D("A" * cells, config=config)
        bardo = BardoFrontierGrid2D("A" * cells, config=config)

        pulse_a = [0.0] * cells
        pulse_a[3] = 0.9
        pulse_a[20] = 0.9
        pulse_b = [0.0] * cells
        pulse_b[11] = 0.9
        pulses = []
        for tick in range(16):
            if tick == 0:
                pulses.append(pulse_a)
            elif tick == 8:
                pulses.append(pulse_b)
            else:
                pulses.append([0.0] * cells)

        for pulse in pulses:
            dense.step(pulse)
            dirty.step(pulse)
            bardo.step(pulse)
            self.assertEqual(bardo.state_string(), dense.state_string())
            self.assertEqual(dirty.state_string(), dense.state_string())
            self.assertEqual(bardo.transitions, dense.transitions)
            self.assertEqual(dirty.transitions, dense.transitions)

    def test_candidate_has_no_hidden_node_evaluation_advantage_in_simple_case(self):
        config = self._config()
        cells = config.width * config.height
        dirty = DirtyNodeGrid2D("A" * cells, config=config)
        bardo = BardoFrontierGrid2D("A" * cells, config=config)
        pulse = [0.0] * cells
        pulse[cells // 2] = 0.9

        for item in [pulse] + [[0.0] * cells for _ in range(7)]:
            dirty.step(item)
            bardo.step(item)

        self.assertEqual(bardo.node_evaluations, dirty.node_evaluations)
        self.assertEqual(bardo.scheduled_work_items, dirty.scheduled_work_items)

    def test_frontier_relation_is_first_class(self):
        relation = FrontierRelation(4, 5, "phase_change")
        self.assertEqual(relation.source_site, 4)
        self.assertEqual(relation.destination_site, 5)
        self.assertEqual(relation.cause, "phase_change")

    def test_memory_decay_nonzero_fails_closed(self):
        config = Grid2DConfig(width=5, height=5, memory_decay=0.1)
        with self.assertRaises(ValueError):
            BardoFrontierGrid2D("A" * 25, config=config)


if __name__ == "__main__":
    unittest.main()
