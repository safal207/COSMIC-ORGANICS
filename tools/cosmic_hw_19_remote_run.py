from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tarfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cosmic_hw_18_hil import HilError, run_hil


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path: Path) -> argparse.Namespace:
    resolved = path.resolve()
    config = json.loads(resolved.read_text(encoding="utf-8"))
    required = {
        "bitstream",
        "serial_port",
        "programmer",
        "power_cycle_hook",
        "output_dir",
        "media",
        "operator",
        "board_id",
        "board_revision",
        "fpga_marking",
        "confirm_volatile_sram_programming",
    }
    missing = sorted(required - set(config))
    unexpected = sorted(set(config) - required)
    if missing or unexpected:
        raise ValueError(f"config keys invalid: missing={missing}, unexpected={unexpected}")
    if config["confirm_volatile_sram_programming"] is not True:
        raise ValueError("volatile SRAM programming must be explicitly confirmed")
    if config["programmer"] not in {"openFPGALoader", "fujprog"}:
        raise ValueError("programmer must be openFPGALoader or fujprog")
    if not isinstance(config["media"], list) or not config["media"]:
        raise ValueError("media must contain at least one photo or video path")
    for field in ("operator", "board_id", "board_revision", "fpga_marking"):
        if not isinstance(config[field], str) or not config[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    return argparse.Namespace(
        bitstream=Path(config["bitstream"]),
        serial_port=Path(config["serial_port"]),
        programmer=config["programmer"],
        power_cycle_hook=Path(config["power_cycle_hook"]),
        output_dir=Path(config["output_dir"]),
        media=[Path(value) for value in config["media"]],
        operator=config["operator"],
        board_id=config["board_id"],
        board_revision=config["board_revision"],
        fpga_marking=config["fpga_marking"],
        confirm_volatile_sram_programming=True,
    )


def archive_evidence(output_dir: Path) -> dict[str, Any]:
    resolved = output_dir.resolve()
    if not resolved.is_dir() or not any(resolved.iterdir()):
        raise RuntimeError("no evidence directory was produced")
    for entry in resolved.rglob("*"):
        if entry.is_symlink():
            raise RuntimeError(f"symlink is forbidden in evidence archive: {entry}")
        if not entry.is_dir() and not entry.is_file():
            raise RuntimeError(f"non-regular evidence entry: {entry}")
    archive = resolved.parent / f"{resolved.name}.tar.gz"
    if archive.exists():
        raise RuntimeError(f"refusing to overwrite evidence archive: {archive}")
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(resolved, arcname=resolved.name, recursive=True)
    digest = sha256_file(archive)
    digest_path = Path(f"{archive}.sha256")
    digest_path.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return {
        "path": str(archive),
        "bytes": archive.stat().st_size,
        "sha256": digest,
        "sha256_file": str(digest_path),
    }


def execute(config_path: Path) -> dict[str, Any]:
    args = load_config(config_path)
    if args.output_dir.resolve() == ROOT or args.output_dir.resolve().is_relative_to(ROOT):
        raise ValueError("output_dir must be outside the repository")
    result = run_hil(args)
    archive = archive_evidence(args.output_dir)
    passed = result.get("passed") is True
    return {
        "experiment_id": "COSMIC-HW-19/v0.1",
        "protocol": "COSMIC-HW-19-REMOTE-HIL/v0.1",
        "completed_at": utc_now(),
        "hw18_decision": result.get("decision"),
        "physical_board_executed": result.get("physical_board_executed") is True,
        "successful_repetitions": result.get("successful_repetitions", 0),
        "evidence_archive": archive,
        "decision": "REMOTE_HIL_EVIDENCE_READY" if passed else "REMOTE_HIL_FAILED",
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-command remote-operator wrapper for the exact HW-18 ULX3S HIL run."
    )
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = execute(args.config)
    except HilError as error:
        result = {
            "experiment_id": "COSMIC-HW-19/v0.1",
            "completed_at": utc_now(),
            "decision": "REMOTE_HIL_FAILED",
            "hw18_decision": error.decision,
            "physical_board_executed": False,
            "passed": False,
            "error": str(error),
        }
    except (FileNotFoundError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        result = {
            "experiment_id": "COSMIC-HW-19/v0.1",
            "completed_at": utc_now(),
            "decision": "REMOTE_HIL_FAILED",
            "physical_board_executed": False,
            "passed": False,
            "error": str(error),
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
