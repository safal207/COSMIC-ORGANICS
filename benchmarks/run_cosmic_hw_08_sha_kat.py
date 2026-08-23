from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from benchmarks.cosmic_hw_08_kat import generate_full_batch_kats, sha256_one_block_padding

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / "rtl" / "cosmic_hw_08_sha256.v"


def padded_hex(msg: bytes) -> str:
    return sha256_one_block_padding(msg).hex()


def build_vectors():
    vectors = [
        (padded_hex(b""), hashlib.sha256(b"").hexdigest(), "empty"),
        (padded_hex(b"abc"), hashlib.sha256(b"abc").hexdigest(), "abc"),
    ]
    for v in generate_full_batch_kats():
        msg = bytes.fromhex(v.message_hex)
        vectors.append((padded_hex(msg), v.digest_hex, f"kat-{v.sequence}"))
    return vectors


def tb_text() -> str:
    lines = [
        "`timescale 1ns/1ps",
        "module tb;",
        "reg clk=0, reset=1, block_valid=0, digest_ready=1;",
        "reg [511:0] block_data=0;",
        "wire block_ready, digest_valid, busy;",
        "wire [255:0] digest_data; wire [6:0] round_count;",
        "integer watchdog=0;",
        "cosmic_sha256_iterative dut(.clk(clk),.reset(reset),.block_valid(block_valid),.block_ready(block_ready),.block_data(block_data),.digest_valid(digest_valid),.digest_ready(digest_ready),.digest_data(digest_data),.round_count(round_count),.busy(busy));",
        "always #5 clk=~clk;",
        "always @(posedge clk) begin watchdog=watchdog+1; if(watchdog>20000) begin $display(\"TIMEOUT busy=%0d ready=%0d digest_valid=%0d round=%0d\",busy,block_ready,digest_valid,round_count); $fatal(1); end end",
        "task runvec; input [511:0] blk; input [255:0] exp; input integer idx; begin",
        "  while(!block_ready) @(posedge clk);",
        "  @(negedge clk); block_data=blk; block_valid=1;",
        "  @(posedge clk);",
        "  @(negedge clk); block_valid=0;",
        "  while(!digest_valid) @(posedge clk);",
        "  #1;",
        "  if(digest_data!==exp) begin $display(\"FAIL idx=%0d got=%064h exp=%064h round=%0d\",idx,digest_data,exp,round_count); $fatal(1); end",
        "  @(posedge clk);",
        "end endtask",
        "integer i; initial begin repeat(3) @(posedge clk); @(negedge clk); reset=0;",
    ]
    for i, (blk, dig, _name) in enumerate(build_vectors()):
        lines.append(f"runvec(512'h{blk},256'h{dig},{i});")
    lines += [f'$display("PASS vectors={len(build_vectors())}");', "$finish; end", "endmodule"]
    return "\n".join(lines)


def main() -> None:
    tb = Path("/tmp/cosmic_hw08_sha_kat_tb.v")
    out = Path("/tmp/cosmic_hw08_sha_kat.out")
    tb.write_text(tb_text())
    subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(out), str(RTL), str(tb)], check=True)
    proc = subprocess.run(["vvp", str(out)], check=True, text=True, capture_output=True, timeout=30)
    print(proc.stdout.strip())
    assert f"PASS vectors={len(build_vectors())}" in proc.stdout


if __name__ == "__main__":
    main()
