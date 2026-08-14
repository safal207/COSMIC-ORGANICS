import unittest

from morphos.simulator import Lattice, Phase, SimulationConfig, demo


class MorphosZeroTests(unittest.TestCase):
    def test_positive_pulses_increase_order(self):
        lattice = Lattice(size=5)
        before = lattice.order_parameter
        lattice.run([0.5, 0.5])
        self.assertGreater(lattice.order_parameter, before)
        self.assertEqual(lattice.phase_string(), "CCCCC")

    def test_negative_pulses_amorphize_crystalline_state(self):
        lattice = Lattice(size=4, initial=Phase.CRYSTALLINE)
        lattice.run([-0.5, -0.5])
        self.assertEqual(lattice.phase_string(), "AAAA")

    def test_one_tick_moves_only_one_adjacent_phase(self):
        lattice = Lattice(size=3)
        lattice.step(100.0)
        self.assertEqual(lattice.phase_string(), "MMM")

    def test_updates_are_synchronous(self):
        config = SimulationConfig(coupling=1.0, crystallize_threshold=0.4)
        lattice = Lattice(
            size=3,
            initial=[Phase.CRYSTALLINE, Phase.AMORPHOUS, Phase.AMORPHOUS],
            config=config,
        )
        lattice.step(0.0)
        self.assertEqual(lattice.phase_string(), "MMA")

    def test_digest_is_deterministic(self):
        a = demo()
        b = demo()
        self.assertEqual(a, b)
        self.assertEqual(len(a["state_digest"]), 64)

    def test_invalid_dimensions_fail(self):
        with self.assertRaises(ValueError):
            Lattice(size=0)
        with self.assertRaises(ValueError):
            Lattice(size=2, initial=[Phase.AMORPHOUS])


if __name__ == "__main__":
    unittest.main()
