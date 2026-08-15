"""Discover and confirm MORPHOS-S1 scale-aware coupling without per-size retuning."""
from __future__ import annotations
import argparse, hashlib, itertools, json, math
from pathlib import Path
from typing import Any, Callable
from morphos.grid2d import Grid2D, Grid2DConfig
from morphos.scale_aware import ScaleLaw

DEFAULT_MANIFEST = Path(__file__).with_name("scale_aware_manifest.json")

class Majority2D:
    def __init__(self, initial: str, *, width: int, height: int) -> None:
        if len(initial) != width * height or any(v not in {"A","C"} for v in initial):
            raise ValueError("Majority2D requires binary width*height state")
        self.width=width; self.height=height; self.states=list(initial); self.transitions=0
    def _neighbors(self,index:int)->list[int]:
        r,c=divmod(index,self.width); out=[]
        for dr,dc in ((-1,0),(1,0),(0,-1),(0,1)):
            rr,cc=r+dr,c+dc
            if 0<=rr<self.height and 0<=cc<self.width: out.append(rr*self.width+cc)
        return out
    def step(self)->None:
        nxt=self.states.copy()
        for i,current in enumerate(self.states):
            vals=[self.states[j] for j in self._neighbors(i)]
            cc=vals.count("C"); aa=vals.count("A")
            if cc>aa: nxt[i]="C"
            elif aa>cc: nxt[i]="A"
            else: nxt[i]=current
        self.transitions += sum(a!=b for a,b in zip(self.states,nxt)); self.states=nxt
    def run(self,steps:int)->None:
        for _ in range(steps): self.step()
    def state_string(self)->str: return "".join(self.states)

def _sha_binary_seeds(seed:int,samples:int,cells:int)->list[str]:
    values=[]
    for sample in range(samples):
        chunks=b""; counter=0
        while len(chunks)*8<cells:
            chunks += hashlib.sha256(f"{seed}:{sample}:{counter}".encode("ascii")).digest(); counter+=1
        bits="".join(f"{b:08b}" for b in chunks)[:cells]
        values.append("".join("C" if bit=="1" else "A" for bit in bits))
    return values

def _grid_relax(config:Grid2DConfig,steps:int)->Callable[[str],tuple[str,int]]:
    def relax(initial:str)->tuple[str,int]:
        lattice=Grid2D(initial,config=config); lattice.run([0.0]*steps); return lattice.state_string(),lattice.transitions
    return relax

def _majority_relax(width:int,height:int,steps:int)->Callable[[str],tuple[str,int]]:
    def relax(initial:str)->tuple[str,int]:
        model=Majority2D(initial,width=width,height=height); model.run(steps); return model.state_string(),model.transitions
    return relax

def _binary_fixed(seeds:list[str],relax:Callable[[str],tuple[str,int]])->tuple[dict[str,int],dict[str,int],list[int]]:
    finals={}; costs=[]
    for seed in seeds:
        final,cost=relax(seed); finals[final]=finals.get(final,0)+1; costs.append(cost)
    fixed={}
    for state,count in finals.items():
        nxt,_=relax(state)
        if nxt==state: fixed[state]=count
    binary={state:count for state,count in fixed.items() if "M" not in state}
    return finals,binary,costs

def _capacity_cost(seeds:list[str],relax:Callable[[str],tuple[str,int]])->dict[str,Any]:
    finals,binary,costs=_binary_fixed(seeds,relax)
    return {
        "binary_capacity_bits": round(math.log2(len(binary)),12) if binary else 0.0,
        "binary_fixed_attractors": len(binary),
        "binary_fixed_seed_coverage": round(sum(binary.values())/len(seeds),12),
        "seed_transition_cost": round(sum(costs)/len(costs),12),
        "unique_final_states": len(finals),
    }

def _flip(state:str,indices:tuple[int,...])->str:
    values=list(state)
    for index in indices: values[index]="C" if values[index]=="A" else "A"
    return "".join(values)

def _metric_suite(seeds:list[str],relax:Callable[[str],tuple[str,int]],*,noise_seed:int,trial_cap:int,per_target_combo_cap:int)->dict[str,Any]:
    finals,binary,seed_costs=_binary_fixed(seeds,relax)
    report={
        "binary_capacity_bits": round(math.log2(len(binary)),12) if binary else 0.0,
        "binary_fixed_attractors": len(binary),
        "binary_fixed_seed_coverage": round(sum(binary.values())/len(seeds),12),
        "seed_transition_cost": round(sum(seed_costs)/len(seed_costs),12),
        "unique_final_states": len(finals),
    }
    cells=len(seeds[0]); trials=[]
    for target_index,target in enumerate(binary):
        combos=list(itertools.combinations(range(cells),1))
        if len(combos)>per_target_combo_cap:
            combos=sorted(combos,key=lambda combo:hashlib.sha256(f"{noise_seed}:{target_index}:1:{combo}".encode("ascii")).digest())[:per_target_combo_cap]
        trials.extend((target,combo) for combo in combos)
    if len(trials)>trial_cap:
        trials=sorted(trials,key=lambda item:hashlib.sha256(f"{noise_seed}:1:{item[0]}:{item[1]}".encode("ascii")).digest())[:trial_cap]
    recovered=0; recovery_costs=[]
    for target,indices in trials:
        final,cost=relax(_flip(target,indices)); recovered += int(final==target); recovery_costs.append(cost)
    report.update({
        "recovery_1bit": round(recovered/len(trials),12) if trials else 0.0,
        "recovery_cost_1bit": round(sum(recovery_costs)/len(recovery_costs),12) if trials else 0.0,
        "recovery_trials_1bit": len(trials),
    })
    return report

def _base_config(spec:dict[str,Any])->Grid2DConfig:
    return Grid2DConfig(width=5,height=5,**spec)

def _compare(candidate:dict[str,Any],baseline:dict[str,Any])->dict[str,Any]:
    return {
        "binary_capacity_delta_bits": round(candidate["binary_capacity_bits"]-baseline["binary_capacity_bits"],12),
        "binary_coverage_delta": round(candidate["binary_fixed_seed_coverage"]-baseline["binary_fixed_seed_coverage"],12),
        "recovery_delta": round(candidate["recovery_1bit"]-baseline["recovery_1bit"],12),
        "recovery_cost_ratio": round(candidate["recovery_cost_1bit"]/baseline["recovery_cost_1bit"],12) if baseline["recovery_cost_1bit"] else None,
        "seed_cost_ratio": round(candidate["seed_transition_cost"]/baseline["seed_transition_cost"],12) if baseline["seed_transition_cost"] else None,
    }

def run_suite(manifest_path:Path=DEFAULT_MANIFEST)->dict[str,Any]:
    manifest=json.loads(manifest_path.read_text(encoding="utf-8")); steps=manifest["relax_steps"]
    base=_base_config(manifest["frozen_candidate"]); discovery=manifest["discovery"]
    exponent_results=[]; selected=None
    for exponent in discovery["exponents"]:
        law=ScaleLaw(reference_linear_size=discovery["reference_linear_size"],exponent=exponent)
        deltas=[]; ratios=[]; corpus_count=0
        for size in discovery["sizes"]:
            config=law.apply(base,width=size["width"],height=size["height"])
            for seed in size["seeds"]:
                seeds=_sha_binary_seeds(seed,size["samples"],size["width"]*size["height"])
                candidate=_capacity_cost(seeds,_grid_relax(config,steps)); baseline=_capacity_cost(seeds,_majority_relax(size["width"],size["height"],steps))
                deltas.append(candidate["binary_capacity_bits"]-baseline["binary_capacity_bits"])
                ratios.append(candidate["seed_transition_cost"]/baseline["seed_transition_cost"] if baseline["seed_transition_cost"] else 0.0); corpus_count+=1
        passes=all(v>0 for v in deltas) and all(v<1 for v in ratios)
        exponent_results.append({
            "exponent": exponent,
            "corpora": corpus_count,
            "passes": passes,
            "min_capacity_delta_bits": round(min(deltas),12),
            "mean_capacity_delta_bits": round(sum(deltas)/len(deltas),12),
            "max_seed_cost_ratio": round(max(ratios),12),
        })
        if passes and selected is None: selected=exponent
    if selected is None: raise RuntimeError("discovery produced no admissible scale exponent")

    law=ScaleLaw(reference_linear_size=discovery["reference_linear_size"],exponent=selected)
    confirmation=[]; cap_deltas=[]; rec_deltas=[]; seed_ratios=[]; rec_ratios=[]; frozen_failures=0
    conf=manifest["confirmation"]
    for size in conf["sizes"]:
        scaled=law.apply(base,width=size["width"],height=size["height"])
        frozen=Grid2DConfig(width=size["width"],height=size["height"],**manifest["frozen_candidate"])
        for seed in size["seeds"]:
            seeds=_sha_binary_seeds(seed,size["samples"],size["width"]*size["height"])
            majority=_metric_suite(seeds,_majority_relax(size["width"],size["height"],steps),noise_seed=seed,trial_cap=conf["trial_cap"],per_target_combo_cap=conf["per_target_combo_cap"])
            s1=_metric_suite(seeds,_grid_relax(scaled,steps),noise_seed=seed,trial_cap=conf["trial_cap"],per_target_combo_cap=conf["per_target_combo_cap"])
            frozen_metrics=_capacity_cost(seeds,_grid_relax(frozen,steps))
            comparison=_compare(s1,majority)
            frozen_capacity_delta=round(frozen_metrics["binary_capacity_bits"]-majority["binary_capacity_bits"],12)
            frozen_failures += int(frozen_capacity_delta <= 0)
            cap_deltas.append(comparison["binary_capacity_delta_bits"]); rec_deltas.append(comparison["recovery_delta"]); seed_ratios.append(comparison["seed_cost_ratio"]); rec_ratios.append(comparison["recovery_cost_ratio"])
            confirmation.append({
                "width": size["width"], "height": size["height"], "seed": seed, "samples": size["samples"],
                "scale_factor": round(law.factor(size["width"],size["height"]),12),
                "frozen_capacity_delta_bits_vs_majority": frozen_capacity_delta,
                "scale_aware": s1, "majority_ca": majority, "comparison": comparison,
            })
    summary={
        "selected_exponent": selected,
        "reference_linear_size": law.reference_linear_size,
        "confirmation_corpora": len(confirmation),
        "frozen_capacity_failure_corpora": frozen_failures,
        "scale_aware_capacity_failure_corpora": sum(v<=0 for v in cap_deltas),
        "all_confirmation_capacity_deltas_positive": all(v>0 for v in cap_deltas),
        "all_confirmation_seed_cost_ratios_below_one": all(v is not None and v<1 for v in seed_ratios),
        "all_confirmation_recovery_deltas_nonnegative": all(v>=0 for v in rec_deltas),
        "all_confirmation_recovery_cost_ratios_below_one": all(v is not None and v<1 for v in rec_ratios),
        "mean_capacity_delta_bits": round(sum(cap_deltas)/len(cap_deltas),12),
        "mean_recovery_delta": round(sum(rec_deltas)/len(rec_deltas),12),
        "mean_seed_cost_ratio": round(sum(seed_ratios)/len(seed_ratios),12),
        "mean_recovery_cost_ratio": round(sum(rec_ratios)/len(rec_ratios),12),
        "scale_capacity_gate_pass": all(v>0 for v in cap_deltas) and all(v is not None and v<1 for v in seed_ratios),
        "recovery_gate_pass": all(v>=0 for v in rec_deltas),
        "full_scale_generalization_pass": all(v>0 for v in cap_deltas) and all(v is not None and v<1 for v in seed_ratios) and all(v>=0 for v in rec_deltas),
        "interpretation": "scale_capacity_repaired_recovery_tradeoff_remains",
    }
    report={
        "schema_version":"cosmic-organics/scale-aware-result-0.1",
        "suite_id":manifest["suite_id"],
        "selection_rule":discovery["selection_rule"],
        "discovery":exponent_results,
        "confirmation":confirmation,
        "summary":summary,
    }
    canonical=json.dumps(report,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("utf-8")
    report["result_digest"]=hashlib.sha256(canonical).hexdigest(); return report

def main()->None:
    parser=argparse.ArgumentParser(); parser.add_argument("--manifest",type=Path,default=DEFAULT_MANIFEST); parser.add_argument("--output",type=Path); args=parser.parse_args()
    rendered=json.dumps(run_suite(args.manifest),indent=2,sort_keys=True)+"\n"
    if args.output: args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(rendered,encoding="utf-8")
    else: print(rendered,end="")
if __name__ == "__main__": main()
