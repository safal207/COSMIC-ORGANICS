from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

from benchmarks.cosmic_hw_12_oracle import RFC_STYLE_KATS, TEST_KEY, frozen_pairs

ROOT = Path(__file__).resolve().parents[1]


def write_mem(path: Path, values: list[int], hex_digits: int) -> None:
    path.write_text("\n".join(f"{value:0{hex_digits}x}" for value in values) + "\n", encoding="utf-8")


def normalize_key(key: bytes) -> bytes:
    if len(key) > 64:
        raise ValueError("HW-12 KAT runner only freezes keys <=64 bytes")
    return key + bytes(64 - len(key))


def vectors() -> list[tuple[bytes, bytes, bytes]]:
    rows: list[tuple[bytes, bytes, bytes]] = []
    for kat in RFC_STYLE_KATS:
        rows.append((bytes(kat["key"]), bytes(kat["message"]), bytes.fromhex(str(kat["expected_hex"]))))
    for row in frozen_pairs():
        rows.append((TEST_KEY, bytes.fromhex(str(row["record_hex"])), bytes.fromhex(str(row["tag_hex"]))))
    if len(rows) != 446:
        raise RuntimeError(f"frozen HW-12 KAT count mismatch: {len(rows)}")
    if any(len(message) > 55 for _, message, _ in rows):
        raise RuntimeError("frozen HW-12 short-message boundary exceeded")
    return rows


def make_tb(count: int, key_mem: Path, msg_mem: Path, len_mem: Path, tag_mem: Path) -> str:
    return f'''`timescale 1ns/1ps
module cosmic_hw12_hmac_kat_tb;
localparam integer N={count};
reg clk=0, reset=1, message_valid=0, tag_ready=0;
reg [511:0] key_block=0;
reg [439:0] message_data=0;
reg [5:0] message_len=0;
wire message_ready,tag_valid,busy,compression_busy,compression_accept_pulse;
wire [255:0] tag_data;
wire [2:0] compression_count;
wire [6:0] compression_round_count;
reg [511:0] key_vectors[0:N-1];
reg [439:0] msg_vectors[0:N-1];
reg [5:0] len_vectors[0:N-1];
reg [255:0] tag_vectors[0:N-1];
integer i,watchdog,total_compressions=0;
always #5 clk=~clk;
always @(posedge clk) if(!reset && compression_accept_pulse) total_compressions=total_compressions+1;

cosmic_hmac_sha256_shortmsg_safe dut(
 .clk(clk),.reset(reset),.message_valid(message_valid),.message_ready(message_ready),
 .key_block(key_block),.message_data(message_data),.message_len(message_len),
 .tag_valid(tag_valid),.tag_ready(tag_ready),.tag_data(tag_data),.busy(busy),
 .compression_count(compression_count),.compression_busy(compression_busy),
 .compression_round_count(compression_round_count),.compression_accept_pulse(compression_accept_pulse));

task run_vector; input integer idx; begin
 watchdog=0;
 while(!message_ready) begin @(posedge clk); #1; watchdog=watchdog+1; if(watchdog>1000) $fatal(1,"message-ready watchdog idx=%0d",idx); end
 @(negedge clk); key_block=key_vectors[idx]; message_data=msg_vectors[idx]; message_len=len_vectors[idx]; message_valid=1; tag_ready=0;
 @(posedge clk); #1;
 @(negedge clk); message_valid=0;
 watchdog=0;
 while(!tag_valid) begin @(posedge clk); #1; watchdog=watchdog+1; if(watchdog>1000) $fatal(1,"tag watchdog idx=%0d state=%0d count=%0d",idx,dut.state,compression_count); end
 if(tag_data!==tag_vectors[idx]) $fatal(1,"HMAC mismatch idx=%0d got=%064h exp=%064h",idx,tag_data,tag_vectors[idx]);
 if(compression_count!==3'd4) $fatal(1,"compression count mismatch idx=%0d got=%0d",idx,compression_count);
 // Hold tag under backpressure for two active edges and require stability.
 repeat(2) begin @(posedge clk); #1; if(!tag_valid) $fatal(1,"tag valid dropped under backpressure idx=%0d",idx); if(tag_data!==tag_vectors[idx]) $fatal(1,"tag changed under backpressure idx=%0d",idx); end
 @(negedge clk); tag_ready=1;
 @(posedge clk); #1;
 @(negedge clk); tag_ready=0;
end endtask

initial begin
 $readmemh("{key_mem}",key_vectors);
 $readmemh("{msg_mem}",msg_vectors);
 $readmemh("{len_mem}",len_vectors);
 $readmemh("{tag_mem}",tag_vectors);
 repeat(4) @(posedge clk); @(negedge clk); reset=0;
 for(i=0;i<N;i=i+1) run_vector(i);
 if(total_compressions != N*4) $fatal(1,"global compression count mismatch got=%0d exp=%0d",total_compressions,N*4);
 $display("COSMIC_HW12_HMAC_KAT PASS vectors=%0d compressions=%0d frozen_roots=444",N,total_compressions);
 $finish;
end
endmodule
'''


def main() -> None:
    rows = vectors()
    with tempfile.TemporaryDirectory(prefix="cosmic-hw12-hmac-kat-") as td:
        tmp = Path(td)
        key_path = tmp / "keys.mem"
        msg_path = tmp / "messages.mem"
        len_path = tmp / "lengths.mem"
        tag_path = tmp / "tags.mem"
        write_mem(key_path, [int.from_bytes(normalize_key(k), "big") for k, _, _ in rows], 128)
        write_mem(msg_path, [int.from_bytes(m + bytes(55-len(m)), "big") for _, m, _ in rows], 110)
        write_mem(len_path, [len(m) for _, m, _ in rows], 2)
        write_mem(tag_path, [int.from_bytes(t, "big") for _, _, t in rows], 64)
        tb = tmp / "tb.v"
        tb.write_text(make_tb(len(rows), key_path, msg_path, len_path, tag_path), encoding="utf-8")
        sim = tmp / "sim.out"
        compile_cmd = [
            "iverilog", "-g2012", "-s", "cosmic_hw12_hmac_kat_tb", "-o", str(sim),
            str(ROOT / "rtl" / "cosmic_hw_12_hmac.v"),
            str(ROOT / "rtl" / "cosmic_hw_12_hmac_safe.v"),
            str(tb),
        ]
        subprocess.run(compile_cmd, check=True)
        proc = subprocess.run(["vvp", str(sim)], check=True, text=True, capture_output=True)
        print(proc.stdout, end="")
        if "COSMIC_HW12_HMAC_KAT PASS vectors=446 compressions=1784 frozen_roots=444" not in proc.stdout:
            raise RuntimeError("HW-12 HMAC PASS marker missing")


if __name__ == "__main__":
    main()
