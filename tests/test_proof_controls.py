"""Historical BARDO-PROOF-03/v0.1 control tests.

v0.1 was executed and failed before any Bardo candidate existed. The proof
model did not authenticate disclosed local phase facts against a committed
pre-state. The RED result is retained in Git history and Issue #62. Active
controls moved to test_proof_controls_v02.py.
"""
import unittest


@unittest.skip(
    "BARDO-PROOF-03/v0.1 superseded after pre-candidate control RED; see Issue #62"
)
class HistoricalProofControlV01Tests(unittest.TestCase):
    def test_v01_is_not_an_active_protocol(self):
        self.fail("historical v0.1 must never execute as an active proof gate")


if __name__ == "__main__":
    unittest.main()
