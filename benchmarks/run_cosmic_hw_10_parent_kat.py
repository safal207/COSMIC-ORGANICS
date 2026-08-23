from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

from benchmarks.cosmic_hw_07_candidate import build_oracle
from benchmarks.cosmic_hw_08_candidate import expected_commitments
from benchmarks.cosmic_hw_10_oracle import build_tree, parent_hash

VECTORS = 128


def frozen_parent_vectors() -> list[tuple[bytes, bytes, bytes]]:
    execution = build_oracle()
    commitments = expected_commitments(execution)
    digests = [int(x).to_bytes(32, "big") for x in commitments["digests"]]
    seq_counts = [int(x) for x in commitments["seq_digest_counts"]]

    out: list[tuple[bytes, bytes, bytes]] = []
    cursor = 0
    for source_sequence, count in enumerate(seq_counts):
        seq_digests = digests[cursor : cursor + count]
        cursor += count
        tree_ordinal = 0
        for start in range(0, count, 16):
            tree = build_tree(source_sequence, tree_ordinal, seq_digests[start : start + 16])
            for level in range(4):
                children = tree.nodes[level]
                parents = tree.nodes[level + 1]
                for idx in range(0, len(children), 2):
                    left = children[idx]
                    right = children[idx + 1]
                    expected = parents[idx // 2]
                    assert parent_hash(left, right) == expected
                    out.append((left, right, expected))
                    if len(out) == VECTORS:
                        return out
            tree_ordinal += 1
    raise RuntimeError(f"only derived {len(out)} vectors")


def make_tb(vectors: list[tuple[bytes, bytes, bytes]]) -> str:
    calls = []
    for left, right, expected in vectors:
        calls.append(
            f"run_vector(256'h{left.hex()},256'h{right.hex()},256'h{expected.hex()});"
        )
    body = "\n  ".join(calls)
    return f'''`timescale 1ns/1ps
module cosmic_hw10_parent_kat_tb;
reg clk=0, reset=1, parent_valid=0, digest_ready=1;
reg [255:0] left_digest=0, right_digest=0;
wire parent_ready, digest_valid, busy;
wire [255:0] digest_data;
wire [7:0] round_count;
integer passed=0;
always #5 clk=~clk;

cosmic_sha256_parent65_iterative dut(
 .clk(clk),.reset(reset),.parent_valid(parent_valid),.parent_ready(parent_ready),
 .left_digest(left_digest),.right_digest(right_digest),
 .digest_valid(digest_valid),.digest_ready(digest_ready),.digest_data(digest_data),
 .busy(busy),.round_count(round_count));

task run_vector;
 input [255:0] l;
 input [255:0] r;
 input [255:0] exp;
 integer watchdog;
 begin
  while(!parent_ready) @(negedge clk);
  @(negedge clk); left_digest=l; right_digest=r; parent_valid=1;
  @(posedge clk); #1;
  @(negedge clk); parent_valid=0;
  watchdog=0;
  while(!digest_valid) begin
   @(posedge clk); #1; watchdog=watchdog+1;
   if(watchdog>140) $fatal(1,"parent SHA watchdog vector=%0d",passed);
  end
  if(digest_data!==exp) $fatal(1,"parent SHA mismatch vector=%0d got=%064h exp=%064h",passed,digest_data,exp);
  if(round_count!==8'd128) $fatal(1,"round count mismatch vector=%0d got=%0d",passed,round_count);
  passed=passed+1;
  @(posedge clk); #1;
 end
endtask

initial begin
 repeat(3) @(posedge clk); @(negedge clk); reset=0;
  {body}
 $display("COSMIC_HW10_PARENT_KAT PASS vectors=%0d",passed);
 $finish;
end
endmodule
'''


def main() -> None:
    vectors = frozen_parent_vectors()
    assert len(vectors) == VECTORS
    # The vectors are anchored in the frozen workload/oracle; print an extra
    # digest so hosted logs identify the exact KAT set independently of RTL.
    fp = hashlib.sha256(
        b"".join(left + right + expected for left, right, expected in vectors)
    ).hexdigest()
    print(f"HW10 parent KAT frozen-workload fingerprint={fp}")

    root = Path(__file__).resolve().parents[1]
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if not iverilog or not vvp:
        raise RuntimeError("iverilog/vvp required")

    with tempfile.TemporaryDirectory(prefix="cosmic-hw10-parent-kat-") as td:
        td_path = Path(td)
        tb = td_path / "tb.v"
        sim = td_path / "sim.out"
        tb.write_text(make_tb(vectors), encoding="utf-8")
        subprocess.run(
            [
                iverilog, "-g2012", "-s", "cosmic_hw10_parent_kat_tb", "-o", str(sim),
                str(root / "rtl" / "cosmic_hw_06.v"),
                str(root / "rtl" / "cosmic_hw_07_receipt.v"),
                str(root / "rtl" / "cosmic_hw_08_sha256.v"),
                str(root / "rtl" / "cosmic_hw_09_multi_sha.v"),
                str(root / "rtl" / "cosmic_hw_10_merkle.v"),
                str(tb),
            ],
            check=True,
            timeout=120,
        )
        proc = subprocess.run([vvp, str(sim)], check=True, text=True, capture_output=True, timeout=120)
        print(proc.stdout, end="")
        if f"COSMIC_HW10_PARENT_KAT PASS vectors={VECTORS}" not in proc.stdout:
            raise RuntimeError("HW-10 parent KAT PASS marker missing")


if __name__ == "__main__":
    main()
