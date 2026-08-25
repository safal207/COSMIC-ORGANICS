from __future__ import annotations

import json
from pathlib import Path

from benchmarks.cosmic_hw_13_candidate import (
    _preservation_ratio,
    recursive_cell_counts,
    summarize_ecp5_cells,
)


def test_blackbox_and_empty_technology_modules_are_counted_as_leaves(tmp_path: Path) -> None:
    netlist = {
        "modules": {
            "top": {
                "cells": {
                    "logic": {"type": "logic_wrapper"},
                    "dsp": {"type": "MULT18X18D"},
                }
            },
            "logic_wrapper": {
                "cells": {
                    "lut": {"type": "LUT4"},
                    "carry": {"type": "CCU2C"},
                    "ff0": {"type": "TRELLIS_FF"},
                    "ff1": {"type": "TRELLIS_FF"},
                }
            },
            "LUT4": {"attributes": {"blackbox": "1"}, "cells": {}},
            "CCU2C": {"attributes": {"whitebox": "0001"}, "cells": {}},
            "TRELLIS_FF": {"cells": {}},
            "MULT18X18D": {"attributes": {"blackbox": 1}, "cells": {}},
        }
    }
    path = tmp_path / "netlist.json"
    path.write_text(json.dumps(netlist), encoding="utf-8")

    counts = recursive_cell_counts(path, "top")

    assert counts == {
        "LUT4": 1,
        "CCU2C": 1,
        "TRELLIS_FF": 2,
        "MULT18X18D": 1,
    }

    summary = summarize_ecp5_cells(counts)
    assert summary["trellis_comb"] == 3  # LUT4 + two LUT4-equivalents in CCU2C
    assert summary["trellis_ff"] == 2
    assert summary["mult18x18d"] == 1
    assert summary["total_leaf_cells"] == 5


def test_absent_control_resource_is_neutral_for_preservation_ratio() -> None:
    assert _preservation_ratio(0, 0) == 1.0
    assert _preservation_ratio(4, 0) == 1.0
    assert _preservation_ratio(98, 100) == 0.98
