from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time
from benchmarks.cosmic_board_01_oracle import build_oracle
from benchmarks.cosmic_hw_15_candidate import git_blob_sha, looks_like_capacity_failure, parse_utilization, recursive_cell_counts, require_tool, run_cmd, summarize_ecp5_cells
from tools.cosmic_board_01_verify import TranscriptError, verify_transcript
ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / 'benchmarks' / 'cosmic_board_01_manifest.json'
PLL_PATH = ROOT / 'rtl' / 'cosmic_board_01_pll.v'
TOP_PATH = ROOT / 'rtl' / 'cosmic_board_01_ulx3s.v'
CONSTRAINTS_PATH = ROOT / 'constraints' / 'cosmic_board_01_ulx3s.lpf'
HOST_VERIFIER_PATH = ROOT / 'tools' / 'cosmic_board_01_verify.py'
PROCESSOR_SOURCES = [ROOT / 'rtl' / 'cosmic_hw_06.v', ROOT / 'rtl' / 'cosmic_hw_07_receipt.v', ROOT / 'rtl' / 'cosmic_hw_08_sha256.v']
BOARD_SOURCES = PROCESSOR_SOURCES + [PLL_PATH, TOP_PATH]
PROFILE_TOP = 'cosmic_hw08_sparse_receipt_sha256'
BOARD_TOP = 'cosmic_board_01_ulx3s'
DEVICE_CAPACITY = {'comb': 83640, 'ff': 83640, 'mult': 156}

def load_manifest() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    if manifest['experiment_id'] != 'COSMIC-BOARD-01A/v0.1':
        raise RuntimeError('BOARD-01A manifest mismatch')
    if manifest['parent']['source_head'] != '0bbc07d85556a861c9595b869b1f8922e419f0a1':
        raise RuntimeError('BOARD-01A parent moved')
    if manifest['parent']['selected_profile'] != 'PROOF_EDGE_SHA1_NODSP':
        raise RuntimeError('BOARD-01A selected profile moved')
    board = manifest['board']
    if board != {'id': 'ULX3S_85F', 'fpga': 'LFE5U-85F-6BG381C', 'architecture': 'ECP5', 'density_flag': '--85k', 'package': 'CABGA381', 'speed_grade': 6, 'input_clock_mhz': 25.0, 'core_clock_mhz': 10.0, 'idcode': '0x41113043', 'programmer': 'ujprog', 'uart_baud': 115200, 'larger_device_fallback_allowed': False, 'different_board_fallback_allowed': False}:
        raise RuntimeError('BOARD-01A target moved')
    if manifest['placement_seeds'] != [1601, 1602, 1603, 1604, 1605]:
        raise RuntimeError('BOARD-01A seed set moved')
    return manifest

def source_preservation_gate(manifest: dict) -> dict:
    blob_checks: dict[str, dict] = {}
    for relative, expected in manifest['selected_profile']['inherited_source_git_blobs'].items():
        path = ROOT / relative
        actual = git_blob_sha(path) if path.exists() else None
        blob_checks[relative] = {'expected': expected, 'actual': actual, 'match': actual == expected}
    pll_hash = sha256(PLL_PATH.read_bytes()).hexdigest() if PLL_PATH.exists() else None
    top_text = TOP_PATH.read_text(encoding='utf-8') if TOP_PATH.exists() else ''
    constraint_text = CONSTRAINTS_PATH.read_text(encoding='utf-8') if CONSTRAINTS_PATH.exists() else ''
    required_top_tokens = ['module cosmic_board_01_ulx3s', 'cosmic_board_01_pll pll', 'cosmic_hw08_sparse_receipt_sha256 profile', '.stimulus_bus(stimulus_state)', '.digest_data(digest_data)', 'cosmic_board_01_uart_tx', 'frame_crc']
    required_constraints = {'clk_25mhz': 'G2', 'ftdi_rxd': 'L4', 'ftdi_txd': 'M1', 'btn_reset_start': 'R1', 'led[7]': 'H3', 'led[6]': 'E1', 'led[5]': 'E2', 'led[4]': 'D1', 'led[3]': 'D2', 'led[2]': 'C1', 'led[1]': 'C2', 'led[0]': 'B2'}
    constraint_matches = {signal: f'LOCATE COMP "{signal}" SITE "{site}";' in constraint_text for signal, site in required_constraints.items()}
    forbidden_tokens = [token for token in ('$readmemh', '$readmemb', 'a38c0b9d5b1503f66b0e24c598ff41bc', '364fadb92dc4abc21eba864dc98fd264a', 'expected_answer_rom') if token in top_text.lower()]
    result = {'passed': all((row['match'] for row in blob_checks.values())) and pll_hash == manifest['official_pll_reference']['generated_sha256'] and all((token in top_text for token in required_top_tokens)) and all(constraint_matches.values()) and (not forbidden_tokens) and HOST_VERIFIER_PATH.exists(), 'inherited_blob_checks': blob_checks, 'pll_sha256': pll_hash, 'pll_expected_sha256': manifest['official_pll_reference']['generated_sha256'], 'top_tokens_present': {token: token in top_text for token in required_top_tokens}, 'constraint_matches': constraint_matches, 'forbidden_tokens': forbidden_tokens, 'host_verifier_present': HOST_VERIFIER_PATH.exists(), 'exact_profile_instance': 'cosmic_hw08_sparse_receipt_sha256 profile' in top_text, 'checksum_feedback_allowed': False, 'expected_answer_rom_present': bool(forbidden_tokens)}
    if not result['passed']:
        raise RuntimeError(f'BOARD-01A source preservation failed: {result}')
    return result

def make_engine_tb(transcript_path: Path) -> str:
    escaped = str(transcript_path).replace('\\', '\\\\').replace('"', '\\"')
    return f'`timescale 1ns/1ps\nmodule cosmic_board_01_tb;\nreg clk_25mhz=0;\nreg ftdi_txd=1;\nreg btn_reset_start=1;\nwire ftdi_rxd;\nwire [7:0] led;\ninteger fd;\ninteger cycles=0;\nalways #5 clk_25mhz=~clk_25mhz;\ncosmic_board_01_ulx3s #(\n    .SIMULATION(1),\n    .UART_CLKS_PER_BIT(1),\n    .QUIET_CYCLES(32)\n) dut (\n    .clk_25mhz(clk_25mhz),\n    .ftdi_txd(ftdi_txd),\n    .btn_reset_start(btn_reset_start),\n    .ftdi_rxd(ftdi_rxd),\n    .led(led)\n);\ninitial begin\n    fd=$fopen("{escaped}","wb");\n    if(fd==0) $fatal(1,"unable to open transcript output");\n    repeat(12) @(posedge clk_25mhz);\n    @(negedge clk_25mhz); btn_reset_start=0;\nend\nalways @(posedge clk_25mhz) begin\n    cycles=cycles+1;\n    if(dut.uart_byte_valid && dut.uart_byte_ready)\n        $fwrite(fd,"%c",dut.uart_byte_data);\n    if(dut.done) begin\n        $fclose(fd);\n        if(dut.error) $fatal(1,"board controller error asserted");\n        $display("COSMIC_BOARD_01_ENGINE PASS cycles=%0d ticks=%0d receipts=%0d digests=%0d partial=%0d phase=%h active=%h changed=%h dirty=%h",\n            cycles,dut.accepted_ticks,dut.receipt_count,dut.digest_count,\n            dut.final_partial_count,dut.phase_bus,dut.active_mask,\n            dut.changed_mask,dut.dirty_mask);\n        $finish;\n    end\n    if(cycles>2000000) $fatal(1,"board simulation watchdog");\nend\nendmodule\n'

def engine_smoke(tmp: Path) -> dict:
    transcript = tmp / 'board_uart.bin'
    tb = tmp / 'board_tb.v'
    tb.write_text(make_engine_tb(transcript), encoding='utf-8')
    output = tmp / 'board_tb.out'
    command = [require_tool('iverilog'), '-g2012', '-s', 'cosmic_board_01_tb', '-o', str(output)]
    command.extend((str(path) for path in BOARD_SOURCES))
    command.append(str(tb))
    run_cmd(command, timeout=300)
    simulation = run_cmd([require_tool('vvp'), str(output)], timeout=900)
    marker = re.search('COSMIC_BOARD_01_ENGINE PASS cycles=(\\d+) ticks=(\\d+) receipts=(\\d+) digests=(\\d+) partial=(\\d+) phase=([0-9a-fA-F]+) active=([0-9a-fA-F]+) changed=([0-9a-fA-F]+) dirty=([0-9a-fA-F]+)', simulation.stdout)
    if not marker:
        raise RuntimeError('BOARD-01A engine PASS marker missing\n' + simulation.stdout)
    data = transcript.read_bytes()
    verification = verify_transcript(data)
    truncated_rejected = False
    try:
        verify_transcript(data[:-1])
    except TranscriptError:
        truncated_rejected = True
    mutated = bytearray(data)
    mutated[len(mutated) // 2] ^= 1
    mutated_rejected = False
    try:
        verify_transcript(bytes(mutated))
    except TranscriptError:
        mutated_rejected = True
    if not truncated_rejected or not mutated_rejected:
        raise RuntimeError('BOARD-01A transcript negative controls did not fail closed')
    oracle = build_oracle()['summary']
    result = {'passed': True, 'cycles': int(marker.group(1)), 'accepted_ticks': int(marker.group(2)), 'receipt_count': int(marker.group(3)), 'digest_count': int(marker.group(4)), 'final_partial_receipt_count': int(marker.group(5)), 'final_phase_hex': marker.group(6).lower().zfill(32), 'final_active_hex': marker.group(7).lower().zfill(16), 'final_changed_hex': marker.group(8).lower().zfill(16), 'final_dirty_hex': marker.group(9).lower().zfill(16), 'verification': verification, 'negative_controls': {'truncated': truncated_rejected, 'mutated': mutated_rejected}, 'transcript_path': str(transcript)}
    expected_fields = {'accepted_ticks': oracle['ticks'], 'receipt_count': oracle['receipt_count'], 'digest_count': oracle['digest_count'], 'final_partial_receipt_count': oracle['final_partial_receipt_count'], 'final_phase_hex': oracle['final_phase_hex'], 'final_active_hex': oracle['final_active_hex'], 'final_changed_hex': oracle['final_changed_hex'], 'final_dirty_hex': oracle['final_dirty_hex']}
    for key, expected in expected_fields.items():
        if result[key] != expected:
            raise RuntimeError(f'BOARD-01A engine {key} moved: {result[key]} != {expected}')
    return result

def synthesize(top: str, sources: list[Path], output: Path) -> tuple[dict, Path]:
    netlist = output / f'{top}.json'
    source_text = ' '.join((str(path) for path in sources))
    script = f'read_verilog -sv {source_text}; hierarchy -check -top {top}; flatten; synth_ecp5 -nodsp -top {top}; write_json {netlist}'
    run_cmd([require_tool('yosys'), '-q', '-p', script], timeout=3600)
    counts = recursive_cell_counts(netlist, top)
    summary = summarize_ecp5_cells(counts)
    summary.update({'top': top, 'sources': [str(path.relative_to(ROOT)) for path in sources], 'mapping': 'synth_ecp5 -nodsp'})
    if summary['trellis_comb'] <= 0 or summary['trellis_ff'] <= 0:
        raise RuntimeError(f'zero-cell synthesis for {top}')
    if summary['mult18x18d'] != 0:
        raise RuntimeError(f'DSP-free synthesis retained multipliers for {top}')
    return (summary, netlist)

def anti_pruning_gate(manifest: dict, profile: dict, board: dict) -> dict:
    static = manifest['static_phase']
    ratios = {'comb': board['trellis_comb'] / profile['trellis_comb'], 'ff': board['trellis_ff'] / profile['trellis_ff']}
    result = {'passed': ratios['comb'] >= float(static['minimum_harness_comb_fraction_of_profile']) and ratios['ff'] >= float(static['minimum_harness_ff_fraction_of_profile']) and (profile['mult18x18d'] == 0) and (board['mult18x18d'] == 0), 'ratios': ratios, 'thresholds': {'minimum_comb': static['minimum_harness_comb_fraction_of_profile'], 'minimum_ff': static['minimum_harness_ff_fraction_of_profile']}}
    if not result['passed']:
        raise RuntimeError(f'BOARD-01A anti-pruning failed: {result}')
    return result

def parse_clock_fmax(log: str) -> dict:
    matches = re.findall('Max frequency for clock [\'\\"]?([^:\'\\"]+)[\'\\"]?:\\s*([0-9]+(?:\\.[0-9]+)?)\\s*MHz', log)
    clocks = {name: float(value) for name, value in matches}
    generated = [value for name, value in clocks.items() if any((token in name.lower() for token in ('clkout0', 'pll', 'core_clk')))]
    values = generated or list(clocks.values())
    return {'clocks': clocks, 'core_fmax_mhz': min(values) if values else None}

def run_seed(manifest: dict, output_dir: Path, netlist: Path, seed: int) -> dict:
    seed_dir = output_dir / f'seed-{seed}'
    seed_dir.mkdir(parents=True, exist_ok=True)
    config = seed_dir / 'board.config'
    bitstream = seed_dir / 'board.bit'
    route_log = seed_dir / 'nextpnr.log'
    pack_log = seed_dir / 'ecppack.log'
    command = [require_tool('nextpnr-ecp5'), '--85k', '--package', 'CABGA381', '--speed', '6', '--json', str(netlist), '--lpf', str(CONSTRAINTS_PATH), '--textcfg', str(config), '--freq', '10', '--seed', str(seed), '--timing-allow-fail']
    started = time.monotonic()
    timed_out = False
    try:
        process = run_cmd(command, check=False, timeout=3600)
        returncode: int | None = process.returncode
        log = process.stdout
    except subprocess.TimeoutExpired as error:
        timed_out = True
        returncode = None
        raw = error.stdout or ''
        log = raw.decode(errors='replace') if isinstance(raw, bytes) else str(raw)
    runtime = time.monotonic() - started
    route_log.write_text(log, encoding='utf-8')
    routed = not timed_out and returncode == 0 and config.exists() and (config.stat().st_size > 0)
    packed = False
    pack_returncode: int | None = None
    pack_text = ''
    if routed:
        packed_process = run_cmd([require_tool('ecppack'), '--idcode', str(manifest['board']['idcode']), str(config), str(bitstream)], check=False, timeout=300)
        pack_returncode = packed_process.returncode
        pack_text = packed_process.stdout
        pack_log.write_text(pack_text, encoding='utf-8')
        packed = pack_returncode == 0 and bitstream.exists() and (bitstream.stat().st_size > 0)
    parsed = parse_clock_fmax(log)
    core_fmax = parsed['core_fmax_mhz']
    timing_pass = bool(routed and core_fmax is not None and (core_fmax >= 10.0))
    utilization = {'comb': parse_utilization(log, 'TRELLIS_COMB'), 'ff': parse_utilization(log, 'TRELLIS_FF'), 'mult': parse_utilization(log, 'MULT18X18D'), 'ebr': parse_utilization(log, 'DP16KD')}
    return {'seed': seed, 'timed_out': timed_out, 'nextpnr_returncode': returncode, 'runtime_seconds': round(runtime, 3), 'routed': routed, 'packed': packed, 'pack_returncode': pack_returncode, 'timing_10mhz_pass': timing_pass, 'core_fmax_mhz': core_fmax, 'all_clock_fmax_mhz': parsed['clocks'], 'capacity_signal': looks_like_capacity_failure(log), 'utilization': utilization, 'config_bytes': config.stat().st_size if config.exists() else 0, 'bitstream_bytes': bitstream.stat().st_size if bitstream.exists() else 0, 'bitstream_sha256': sha256(bitstream.read_bytes()).hexdigest() if packed else None, 'route_log': str(route_log), 'pack_log': str(pack_log) if pack_log.exists() else None, 'log_tail': '\n'.join(log.splitlines()[-40:]), 'pack_log_tail': '\n'.join(pack_text.splitlines()[-20:])}

def _max_fraction(board_synthesis: dict, seeds: list[dict], resource: str) -> float:
    synthesis_key = {'comb': 'trellis_comb', 'ff': 'trellis_ff'}[resource]
    capacity = DEVICE_CAPACITY[resource]
    fractions = [float(board_synthesis[synthesis_key]) / capacity]
    for seed in seeds:
        row = seed['utilization'].get(resource)
        if row and row.get('fraction') is not None:
            fractions.append(float(row['fraction']))
    return max(fractions)

def summarize_physical(manifest: dict, board_synthesis: dict, seeds: list[dict]) -> dict:
    static = manifest['static_phase']
    successful_routes = sum((bool(seed['routed']) for seed in seeds))
    packed = sum((bool(seed['packed']) for seed in seeds))
    timing = sum((bool(seed['timing_10mhz_pass']) for seed in seeds))
    fmax = [float(seed['core_fmax_mhz']) for seed in seeds if seed['routed'] and seed['core_fmax_mhz'] is not None]
    fractions = {'comb': _max_fraction(board_synthesis, seeds, 'comb'), 'ff': _max_fraction(board_synthesis, seeds, 'ff'), 'mult': 0.0}
    headroom_pass = fractions['comb'] <= float(static['maximum_comb_fraction']) and fractions['ff'] <= float(static['maximum_ff_fraction']) and (board_synthesis['mult18x18d'] == int(static['required_mult18x18d']))
    route_pass = successful_routes >= int(static['minimum_successful_routes']) and packed >= int(static['minimum_nonempty_bitstreams']) and (timing >= int(static['minimum_10mhz_timing_passes']))
    return {'successful_routes': successful_routes, 'packed_bitstreams': packed, 'timing_10mhz_passes': timing, 'headroom_pass': headroom_pass, 'static_board_ready': route_pass and headroom_pass, 'maximum_resource_fractions': fractions, 'core_fmax_mhz': {'values': fmax, 'minimum': min(fmax) if fmax else None, 'median': statistics.median(fmax) if fmax else None, 'maximum': max(fmax) if fmax else None}, 'timeout_count': sum((bool(seed['timed_out']) for seed in seeds)), 'capacity_signal_count': sum((bool(seed['capacity_signal']) for seed in seeds))}

def run(output_dir: Path) -> dict:
    manifest = load_manifest()
    preservation = source_preservation_gate(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cosmic-board-01-') as temp_name:
        temp = Path(temp_name)
        smoke = engine_smoke(temp)
        profile_synthesis, _ = synthesize(PROFILE_TOP, PROCESSOR_SOURCES, temp)
        board_synthesis, board_netlist = synthesize(BOARD_TOP, BOARD_SOURCES, temp)
        anti_pruning = anti_pruning_gate(manifest, profile_synthesis, board_synthesis)
        seeds = [run_seed(manifest, output_dir, board_netlist, int(seed)) for seed in manifest['placement_seeds']]
    physical = summarize_physical(manifest, board_synthesis, seeds)
    decision = 'ULX3S_STATIC_BITSTREAM_SUPPORTED' if physical['static_board_ready'] else 'ULX3S_STATIC_BITSTREAM_NOT_SUPPORTED'
    return {'benchmark_id': 'COSMIC-BOARD-01A-CANDIDATE', 'protocol': 'COSMIC-BOARD-01A/v0.1', 'parent_hw15_source_head': manifest['parent']['source_head'], 'selected_profile': manifest['parent']['selected_profile'], 'board': manifest['board'], 'placement_seeds': manifest['placement_seeds'], 'source_preservation': preservation, 'engine_smoke': smoke, 'profile_synthesis': profile_synthesis, 'board_synthesis': board_synthesis, 'anti_pruning': anti_pruning, 'seeds': seeds, 'physical': physical, 'decision': decision, 'physical_board_executed': False, 'synthetic_combined_score_used': False, 'claim_boundary': manifest['claim_boundary']}

def main() -> None:
    parser = argparse.ArgumentParser(description='Execute the frozen COSMIC-BOARD-01A static ULX3S frontier')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=Path('/tmp/cosmic-board-01-evidence'))
    args = parser.parse_args()
    result = run(args.output_dir)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"COSMIC_BOARD_01A_RESULT decision={result['decision']} routes={result['physical']['successful_routes']}")
if __name__ == '__main__':
    main()
