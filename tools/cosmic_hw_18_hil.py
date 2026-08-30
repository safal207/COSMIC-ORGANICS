from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import select
import shutil
import stat
import subprocess
import sys
import termios
import time
import tty
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cosmic_hw_16_uart_verify import FRAME_BYTES, MAGIC, verify_frame  # noqa: E402


MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_18_manifest.json"
EXPECTED_PARENT_HEAD = "9d17ba05f3bb4ff4bac9c0e28d9b5842bcfbfafe"
EXPECTED_BITSTREAM_SHA256 = (
    "eebd73700bacdb0a29e5b5542834f150810196492218cab9b1f5c4e9158b80b3"
)
EXPECTED_BITSTREAM_BYTES = 1_048_738


class HilError(RuntimeError):
    def __init__(self, decision: str, message: str) -> None:
        super().__init__(message)
        self.decision = decision


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_manifest() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["experiment_id"] != "COSMIC-HW-18/v0.1":
        raise RuntimeError("HW-18 experiment identity moved")
    if manifest["protocol"] != "COSMIC-HW-18-HIL/v0.1":
        raise RuntimeError("HW-18 protocol moved")
    parent = manifest["parent"]
    if parent["source_head"] != EXPECTED_PARENT_HEAD:
        raise RuntimeError("HW-18 parent source head moved")
    if parent["decision"] != "ULX3S_EXTENDED_BUDGET_BITSTREAM_READY":
        raise RuntimeError("HW-18 parent decision moved")
    if parent["canonical_seed"] != 1601:
        raise RuntimeError("HW-18 canonical seed moved")
    if parent["canonical_bitstream_sha256"] != EXPECTED_BITSTREAM_SHA256:
        raise RuntimeError("HW-18 canonical bitstream digest moved")
    if parent["canonical_bitstream_bytes"] != EXPECTED_BITSTREAM_BYTES:
        raise RuntimeError("HW-18 canonical bitstream size moved")
    if manifest["physical_hil_gate"]["cold_repetitions"] != 10:
        raise RuntimeError("HW-18 repetition count moved")
    if manifest["programming"]["persistent_flash_allowed"] is not False:
        raise RuntimeError("HW-18 persistent flash prohibition moved")
    for relative, expected in manifest["inherited_source_blobs"].items():
        if git_blob_sha(ROOT / relative) != expected:
            raise RuntimeError(f"HW-18 inherited source moved: {relative}")
    return manifest


def git_identity() -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return result.stdout.strip()

    status = git("status", "--porcelain=v1", "--untracked-files=all")
    return {
        "repository_root": str(ROOT),
        "head": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "clean": not bool(status),
        "status": status.splitlines(),
    }


def resolve_executable(value: str) -> Path:
    candidate = Path(value)
    resolved = candidate.resolve() if candidate.parent != Path(".") else None
    if resolved and resolved.is_file() and os.access(resolved, os.X_OK):
        return resolved
    found = shutil.which(value)
    if found:
        path = Path(found).resolve()
        if path.is_file() and os.access(path, os.X_OK):
            return path
    raise FileNotFoundError(f"executable not found: {value}")


def require_regular_file(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} is not a regular file: {resolved}")
    return resolved


def require_character_device(path: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        mode = resolved.stat().st_mode
    except FileNotFoundError as error:
        raise FileNotFoundError(f"{label} does not exist: {resolved}") from error
    if not stat.S_ISCHR(mode):
        raise RuntimeError(f"{label} is not a character device: {resolved}")
    return resolved


def verify_bitstream(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    resolved = require_regular_file(path, "bitstream")
    observed = {
        "path": str(resolved),
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }
    parent = manifest["parent"]
    observed["size_match"] = observed["bytes"] == parent["canonical_bitstream_bytes"]
    observed["sha256_match"] = observed["sha256"] == parent["canonical_bitstream_sha256"]
    observed["passed"] = bool(observed["size_match"] and observed["sha256_match"])
    return observed


def build_programmer_command(
    manifest: dict[str, Any], programmer: str, bitstream: Path
) -> tuple[Path, list[str]]:
    templates = manifest["programming"]["allowed_programmers"]
    if programmer not in templates:
        raise ValueError(f"programmer is not allowed: {programmer}")
    executable = resolve_executable(templates[programmer][0])
    command = [
        str(executable),
        *[
            token.replace("{bitstream}", str(bitstream))
            for token in templates[programmer][1:]
        ],
    ]
    if any(token in {"-f", "--flash", "--write-flash"} for token in command):
        raise RuntimeError("persistent flash option is forbidden")
    return executable, command


def run_process(command: list[str], timeout: int) -> dict[str, Any]:
    started = utc_now()
    start = time.monotonic()
    try:
        process = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        returncode: int | None = process.returncode
        output = process.stdout
        timed_out = False
    except subprocess.TimeoutExpired as error:
        raw = error.stdout or ""
        output = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
        returncode = None
        timed_out = True
    return {
        "command": command,
        "started_at": started,
        "completed_at": utc_now(),
        "runtime_seconds": round(time.monotonic() - start, 3),
        "returncode": returncode,
        "timed_out": timed_out,
        "output": output,
        "passed": returncode == 0 and not timed_out,
    }


def wait_for_character_device(path: Path, timeout: int) -> Path:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return require_character_device(path, "serial port")
        except (FileNotFoundError, RuntimeError) as error:
            last_error = error
            time.sleep(0.25)
    raise TimeoutError(f"serial device did not enumerate within {timeout}s: {last_error}")


def configure_serial(fd: int, baud: int) -> None:
    speeds = {115200: termios.B115200}
    if baud not in speeds:
        raise ValueError(f"unsupported baud: {baud}")
    tty.setraw(fd, termios.TCSANOW)
    attributes = termios.tcgetattr(fd)
    attributes[4] = speeds[baud]
    attributes[5] = speeds[baud]
    attributes[2] |= termios.CLOCAL | termios.CREAD | termios.CS8
    attributes[2] &= ~(termios.PARENB | termios.CSTOPB)
    if hasattr(termios, "CRTSCTS"):
        attributes[2] &= ~termios.CRTSCTS
    attributes[6][termios.VMIN] = 0
    attributes[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attributes)
    termios.tcflush(fd, termios.TCIFLUSH)


def extract_frame(data: bytes) -> bytes | None:
    start = data.find(MAGIC)
    if start < 0 or len(data) - start < FRAME_BYTES:
        return None
    return data[start : start + FRAME_BYTES]


def capture_uart(fd: int, timeout: int) -> tuple[bytes, bytes | None]:
    deadline = time.monotonic() + timeout
    captured = bytearray()
    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        readable, _, _ = select.select([fd], [], [], min(0.25, remaining))
        if not readable:
            continue
        chunk = os.read(fd, 4096)
        if chunk:
            captured.extend(chunk)
            frame = extract_frame(bytes(captured))
            if frame is not None:
                return bytes(captured), frame
    return bytes(captured), None


def file_record(path: Path, role: str, root: Path | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    relative = str(resolved.relative_to(root.resolve())) if root else str(resolved)
    return {
        "path": relative,
        "role": role,
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def copy_media(paths: list[Path], output_dir: Path) -> list[dict[str, Any]]:
    media_dir = output_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for index, source_path in enumerate(paths, start=1):
        source = require_regular_file(source_path, "photo/video evidence")
        destination = media_dir / f"{index:02d}_{source.name}"
        shutil.copy2(source, destination)
        records.append(file_record(destination, "photo_or_video", output_dir))
    return records


def evidence_role(path: Path) -> str:
    roles = {
        "power_cycle.log": "power_cycle_log",
        "programmer.log": "programmer_log",
        "raw_uart.bin": "raw_uart_capture",
        "co16_frame.bin": "co16_frame",
        "verifier.json": "decoded_verifier_json",
        "repetition.json": "repetition_result",
    }
    if path.parts and path.parts[0] == "media":
        return "photo_or_video"
    if path.parts and path.parts[0] == "subject":
        return "canonical_bitstream_subject"
    return roles.get(path.name, "power_cycle_hook_evidence")


def inventory_tree(output_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(output_dir.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"symlink is forbidden in evidence: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise RuntimeError(f"non-regular evidence entry: {path}")
        relative = str(path.relative_to(output_dir))
        if relative in seen:
            raise RuntimeError(f"duplicate evidence path: {relative}")
        seen.add(relative)
        records.append(file_record(path, evidence_role(Path(relative)), output_dir))
    return records


def classify_failure(stage: str) -> str:
    classes = {
        "power_cycle": "POWER_CYCLE_FAILURE",
        "serial": "BOARD_NOT_AVAILABLE",
        "programming": "PROGRAMMING_FAILURE",
        "uart": "UART_PROTOCOL_FAILURE",
        "oracle": "BOARD_ORACLE_MISMATCH",
        "evidence": "EVIDENCE_INCOMPLETE",
    }
    return classes.get(stage, "EVIDENCE_INCOMPLETE")


def offline_verify(bitstream: Path) -> dict[str, Any]:
    manifest = load_manifest()
    bitstream_result = verify_bitstream(bitstream, manifest)
    return {
        "experiment_id": manifest["experiment_id"],
        "protocol": manifest["protocol"],
        "checked_at": utc_now(),
        "parent_source_head": manifest["parent"]["source_head"],
        "bitstream": bitstream_result,
        "physical_board_executed": False,
        "decision": "BOARD_NOT_AVAILABLE",
        "passed": False,
        "claim_boundary": manifest["claim_boundary"],
    }


def run_hil(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest()
    if not args.confirm_volatile_sram_programming:
        raise RuntimeError("explicit volatile SRAM programming confirmation is required")
    if not args.operator.strip():
        raise RuntimeError("operator must be non-empty")
    for label in (args.board_id, args.board_revision, args.fpga_marking):
        if not label.strip():
            raise RuntimeError("board identity fields must be non-empty")

    identity = git_identity()
    bitstream = require_regular_file(args.bitstream, "bitstream")
    bitstream_result = verify_bitstream(bitstream, manifest)
    if not bitstream_result["passed"]:
        raise RuntimeError("bitstream does not match the canonical HW-17 subject")
    if not identity["clean"]:
        raise RuntimeError("harness worktree must be clean")

    hook = resolve_executable(str(args.power_cycle_hook))
    programmer_executable, _ = build_programmer_command(
        manifest, args.programmer, bitstream
    )
    try:
        require_character_device(args.serial_port, "serial port")
    except (FileNotFoundError, RuntimeError) as error:
        raise HilError("BOARD_NOT_AVAILABLE", str(error)) from error
    media_sources = [require_regular_file(path, "photo/video evidence") for path in args.media]
    if not media_sources:
        raise RuntimeError("at least one photo or video is required")

    output_dir = args.output_dir.resolve()
    if output_dir == ROOT or output_dir.is_relative_to(ROOT):
        raise RuntimeError("evidence directory must be outside the repository checkout")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"refusing to overwrite non-empty evidence directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    copy_media(media_sources, output_dir)
    subject_dir = output_dir / "subject"
    subject_dir.mkdir(parents=True, exist_ok=False)
    subject_bitstream = subject_dir / "cosmic_hw_17_canonical.bit"
    shutil.copy2(bitstream, subject_bitstream)
    subject_bitstream.chmod(0o444)
    subject_result = verify_bitstream(subject_bitstream, manifest)
    if not subject_result["passed"]:
        raise RuntimeError("copied bitstream subject does not match the canonical HW-17 subject")
    programmer_executable, programmer_command = build_programmer_command(
        manifest, args.programmer, subject_bitstream
    )

    programming = manifest["programming"]
    repetitions_required = int(manifest["physical_hil_gate"]["cold_repetitions"])
    repetitions: list[dict[str, Any]] = []
    decision = "EVIDENCE_INCOMPLETE"
    failure: dict[str, Any] | None = None

    for repetition in range(1, repetitions_required + 1):
        repetition_dir = output_dir / f"repetition-{repetition:02d}"
        repetition_dir.mkdir(parents=True, exist_ok=False)
        row: dict[str, Any] = {
            "repetition": repetition,
            "started_at": utc_now(),
            "cold_power_cycle": False,
            "volatile_programming": False,
            "uart_frame_captured": False,
            "oracle_match": False,
            "passed": False,
        }
        stage = "power_cycle"
        fd: int | None = None
        try:
            cycle_result = run_process(
                [str(hook), str(repetition), str(repetition_dir)],
                int(programming["power_cycle_timeout_seconds"]),
            )
            cycle_log = repetition_dir / "power_cycle.log"
            cycle_log.write_text(cycle_result.pop("output"), encoding="utf-8")
            row["power_cycle"] = cycle_result
            row["cold_power_cycle"] = bool(cycle_result["passed"])
            if not row["cold_power_cycle"]:
                raise RuntimeError("external power-cycle hook failed")

            stage = "evidence"
            row["pre_program_subject"] = verify_bitstream(subject_bitstream, manifest)
            if not row["pre_program_subject"]["passed"]:
                raise RuntimeError("bitstream subject changed after power cycle")

            stage = "serial"
            serial_path = wait_for_character_device(
                args.serial_port, int(programming["serial_enumeration_timeout_seconds"])
            )
            fd = os.open(serial_path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            configure_serial(fd, int(manifest["frozen_uart"]["baud"]))

            stage = "programming"
            program_result = run_process(
                programmer_command, int(programming["program_timeout_seconds"])
            )
            program_log = repetition_dir / "programmer.log"
            program_log.write_text(program_result.pop("output"), encoding="utf-8")
            row["programming"] = program_result
            row["volatile_programming"] = bool(program_result["passed"])
            if not row["volatile_programming"]:
                raise RuntimeError("volatile SRAM programming failed")

            stage = "uart"
            raw, frame = capture_uart(fd, int(programming["uart_capture_timeout_seconds"]))
            raw_path = repetition_dir / "raw_uart.bin"
            raw_path.write_bytes(raw)
            if frame is None:
                raise RuntimeError("complete CO16 UART frame was not captured")
            frame_path = repetition_dir / "co16_frame.bin"
            frame_path.write_bytes(frame)
            row["uart_frame_captured"] = True
            row["frame_sha256"] = hashlib.sha256(frame).hexdigest()

            stage = "oracle"
            try:
                verifier = verify_frame(frame)
            except ValueError as error:
                verifier = {"passed": False, "error": str(error)}
                stage = "uart"
            verifier_path = repetition_dir / "verifier.json"
            write_json(verifier_path, verifier)
            row["oracle_match"] = verifier.get("passed") is True
            if not row["oracle_match"]:
                raise RuntimeError("captured UART frame did not match the frozen oracle")

            row["passed"] = True
        except (OSError, RuntimeError, TimeoutError, ValueError) as error:
            row["error"] = str(error)
            decision = classify_failure(stage)
            failure = {"repetition": repetition, "stage": stage, "error": str(error)}
        finally:
            if fd is not None:
                os.close(fd)
            row["completed_at"] = utc_now()
            row_path = repetition_dir / "repetition.json"
            write_json(row_path, row)
            repetitions.append(row)
        if not row["passed"]:
            break

    successful = sum(bool(row["passed"]) for row in repetitions)
    if successful == repetitions_required and len(repetitions) == repetitions_required:
        decision = "ULX3S_PROOF_EDGE_HIL_SUPPORTED"

    final_subject_result = verify_bitstream(subject_bitstream, manifest)
    if not final_subject_result["passed"]:
        decision = "EVIDENCE_INCOMPLETE"
        failure = {"stage": "evidence", "error": "bitstream subject changed during run"}

    try:
        inventory = inventory_tree(output_dir)
    except RuntimeError as error:
        decision = "EVIDENCE_INCOMPLETE"
        failure = {"stage": "evidence", "error": str(error)}
        inventory = []

    result = {
        "experiment_id": manifest["experiment_id"],
        "protocol": manifest["protocol"],
        "started_at": repetitions[0]["started_at"] if repetitions else utc_now(),
        "completed_at": utc_now(),
        "parent": manifest["parent"],
        "harness_source": identity,
        "environment": {
            "platform": platform.platform(),
            "python": sys.version,
            "programmer": args.programmer,
            "programmer_executable": file_record(programmer_executable, "programmer_binary"),
            "power_cycle_hook": file_record(hook, "power_cycle_hook"),
            "serial_port": str(args.serial_port),
        },
        "operator_attestation": {
            "operator": args.operator,
            "board_id": args.board_id,
            "board_model": manifest["board"]["name"],
            "board_revision": args.board_revision,
            "fpga_marking": args.fpga_marking,
            "volatile_sram_only_confirmed": True,
            "external_power_cycle_hook_used": True,
        },
        "bitstream": {
            "source": bitstream_result,
            "programmed_subject_initial": subject_result,
            "programmed_subject_final": final_subject_result,
        },
        "required_repetitions": repetitions_required,
        "attempted_repetitions": len(repetitions),
        "successful_repetitions": successful,
        "repetitions": repetitions,
        "failure": failure,
        "physical_run_attempted": bool(repetitions),
        "physical_board_executed": any(
            bool(row["volatile_programming"]) for row in repetitions
        ),
        "decision": decision,
        "passed": decision == "ULX3S_PROOF_EDGE_HIL_SUPPORTED",
        "evidence_inventory": sorted(inventory, key=lambda row: row["path"]),
        "claim_boundary": manifest["claim_boundary"],
    }
    write_json(output_dir / "cosmic_hw_18_result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed COSMIC-HW-18 physical ULX3S cold-boot evidence harness."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify_parser = subparsers.add_parser(
        "verify-bitstream", help="Verify the canonical subject without touching hardware."
    )
    verify_parser.add_argument("--bitstream", type=Path, required=True)

    run_parser = subparsers.add_parser(
        "run", help="Execute the frozen ten-repetition physical HIL protocol."
    )
    run_parser.add_argument("--bitstream", type=Path, required=True)
    run_parser.add_argument("--serial-port", type=Path, required=True)
    run_parser.add_argument(
        "--programmer", choices=("openFPGALoader", "fujprog"), required=True
    )
    run_parser.add_argument("--power-cycle-hook", type=Path, required=True)
    run_parser.add_argument("--output-dir", type=Path, required=True)
    run_parser.add_argument("--media", type=Path, action="append", required=True)
    run_parser.add_argument("--operator", required=True)
    run_parser.add_argument("--board-id", required=True)
    run_parser.add_argument("--board-revision", required=True)
    run_parser.add_argument("--fpga-marking", required=True)
    run_parser.add_argument(
        "--confirm-volatile-sram-programming", action="store_true", required=True
    )

    args = parser.parse_args()
    try:
        result = (
            offline_verify(args.bitstream)
            if args.command == "verify-bitstream"
            else run_hil(args)
        )
    except HilError as error:
        result = {
            "experiment_id": "COSMIC-HW-18/v0.1",
            "completed_at": utc_now(),
            "passed": False,
            "physical_board_executed": False,
            "decision": error.decision,
            "error": str(error),
        }
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        result = {
            "experiment_id": "COSMIC-HW-18/v0.1",
            "completed_at": utc_now(),
            "passed": False,
            "physical_board_executed": False,
            "decision": "EVIDENCE_INCOMPLETE",
            "error": str(error),
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
