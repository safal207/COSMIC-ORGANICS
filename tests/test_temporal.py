import json
from pathlib import Path
import unittest

from benchmarks.run_temporal import run_suite
from morphos.simulator import Phase
from morphos.temporal import TemporalConfig, TemporalLattice


ROOT = Path(__file__).resolve().parents[1]


class TemporalLatticeTests(unittest.TestCase):
    def test_repeated_subthreshold_pulses_accumulate(self):
        lattice = TemporalLattice(size=5)
        lattice.run([0.2] * 5)
        self.assertEqual(lattice.phase_string(), "CCCCC")
        self.assertEqual(lattice.transition_count, 10)

    def test_zero_input_is_stable(self):
        lattice = TemporalLattice(size=5)
        lattice.run([0.0] * 10)
        self.assertEqual(lattice.phase_string(), "AAAAA")
        self.assertEqual(lattice.transition_count, 0)

    def test_isolated_subthreshold_pulse_decays(self):
        lattice = TemporalLattice(size=3)
        lattice.run([0.2, 0.0, 0.0, 0.0])
        self.assertEqual(lattice.phase_string(), "AAA")
        self.assertTrue(all(abs(cell.activation) < 0.2 for cell in lattice.cells))

    def test_alternating_pulses_do_not_ratchet(self):
        lattice = TemporalLattice(size=3)
        lattice.run([0.2, -0.2, 0.2, -0.2, 0.2, -0.2])
        self.assertEqual(lattice.phase_string(), "AAA")
        self.assertEqual(lattice.transition_count, 0)

    def test_invalid_decay_fails(self):
        with self.assertRaises(ValueError):
            TemporalConfig(memory_decay=1.01)
        with self.assertRaises(ValueError):
            TemporalConfig(memory_decay=-0.01)

    def test_temporal_result_is_reproducible(self):
        actual = run_suite(ROOT / "benchmarks" / "temporal_manifest.json")
        expected = json.loads(
            (ROOT / "results" / "p1-temporal-v0.1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(actual, expected)

    def test_snapshot_is_deterministic(self):
        left = TemporalLattice(size=2, initial=Phase.AMORPHOUS)
        right = TemporalLattice(size=2, initial=Phase.AMORPHOUS)
        left.run([0.2, 0.2, 0.0])
        right.run([0.2, 0.2, 0.0])
        self.assertEqual(left.snapshot(), right.snapshot())
        self.assertEqual(left.state_digest(), right.state_digest())


if __name__ == "__main__":
    unittest.main()
