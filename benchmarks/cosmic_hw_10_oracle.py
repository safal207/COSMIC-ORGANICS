from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from benchmarks.cosmic_hw_07_candidate import build_oracle
from benchmarks.cosmic_hw_08_candidate import expected_commitments

PROTOCOL = "COSMIC-HW-10/v0.1"
TREE_LEAVES = 16
TREE_LEVELS = 4
PARENT_DOMAIN = b"\x01"
PAD_LEAF = hashlib.sha256(b"COSMIC-HW-10/PAD").digest()


@dataclass(frozen=True)
class TreeOracle:
    source_sequence: int
    tree_ordinal: int
    real_leaf_count: int
    leaves: tuple[bytes, ...]
    nodes: tuple[tuple[bytes, ...], ...]

    @property
    def root(self) -> bytes:
        return self.nodes[-1][0]


def parent_hash(left: bytes, right: bytes) -> bytes:
    if len(left) != 32 or len(right) != 32:
        raise ValueError("Merkle child digest must be 32 bytes")
    return hashlib.sha256(PARENT_DOMAIN + left + right).digest()


def build_tree(source_sequence: int, tree_ordinal: int, real_leaves: list[bytes]) -> TreeOracle:
    if not 1 <= len(real_leaves) <= TREE_LEAVES:
        raise ValueError("real leaf count must be 1..16")
    if any(len(x) != 32 for x in real_leaves):
        raise ValueError("leaf digest must be 32 bytes")

    leaves = tuple(real_leaves + [PAD_LEAF] * (TREE_LEAVES - len(real_leaves)))
    levels: list[tuple[bytes, ...]] = [leaves]
    current = leaves
    while len(current) > 1:
        current = tuple(parent_hash(current[i], current[i + 1]) for i in range(0, len(current), 2))
        levels.append(current)
    assert len(levels) == TREE_LEVELS + 1
    return TreeOracle(
        source_sequence=source_sequence,
        tree_ordinal=tree_ordinal,
        real_leaf_count=len(real_leaves),
        leaves=leaves,
        nodes=tuple(levels),
    )


def proof_fragments(tree: TreeOracle, leaf_ordinal: int) -> list[dict[str, object]]:
    if not 0 <= leaf_ordinal < tree.real_leaf_count:
        raise ValueError("proof only exists for real leaves")
    out: list[dict[str, object]] = []
    idx = leaf_ordinal
    for level in range(TREE_LEVELS):
        sibling_idx = idx ^ 1
        sibling = tree.nodes[level][sibling_idx]
        out.append(
            {
                "source_sequence": tree.source_sequence,
                "tree_ordinal": tree.tree_ordinal,
                "leaf_ordinal": leaf_ordinal,
                "level": level,
                "sibling_is_left": bool(sibling_idx < idx),
                "sibling_hex": sibling.hex(),
            }
        )
        idx //= 2
    return out


def verify_proof(leaf: bytes, fragments: list[dict[str, object]], root: bytes) -> bool:
    value = leaf
    if len(fragments) != TREE_LEVELS:
        return False
    for expected_level, fragment in enumerate(fragments):
        if int(fragment["level"]) != expected_level:
            return False
        sibling = bytes.fromhex(str(fragment["sibling_hex"]))
        if bool(fragment["sibling_is_left"]):
            value = parent_hash(sibling, value)
        else:
            value = parent_hash(value, sibling)
    return value == root


def derive_oracle() -> dict[str, object]:
    execution = build_oracle()
    commitments = expected_commitments(execution)
    digests = [int(x).to_bytes(32, "big") for x in commitments["digests"]]
    seq_counts = [int(x) for x in commitments["seq_digest_counts"]]

    if len(seq_counts) != 320:
        raise RuntimeError("expected 320 frozen source sequences")
    if sum(seq_counts) != len(digests) != 4240:
        raise RuntimeError("frozen digest count mismatch")

    trees: list[TreeOracle] = []
    cursor = 0
    tree_counts_by_sequence: list[int] = []
    digest_counts_by_sequence = list(seq_counts)

    for source_sequence, count in enumerate(seq_counts):
        seq_digests = digests[cursor : cursor + count]
        cursor += count
        tree_count = 0
        for start in range(0, count, TREE_LEAVES):
            chunk = seq_digests[start : start + TREE_LEAVES]
            trees.append(build_tree(source_sequence, tree_count, chunk))
            tree_count += 1
        tree_counts_by_sequence.append(tree_count)

    if cursor != len(digests):
        raise RuntimeError("digest cursor mismatch")

    roots: list[dict[str, object]] = []
    proofs: list[dict[str, object]] = []
    verified = 0
    real_leaves = 0
    padding_leaves = 0

    for tree in trees:
        roots.append(
            {
                "source_sequence": tree.source_sequence,
                "tree_ordinal": tree.tree_ordinal,
                "real_leaf_count": tree.real_leaf_count,
                "root_hex": tree.root.hex(),
            }
        )
        real_leaves += tree.real_leaf_count
        padding_leaves += TREE_LEAVES - tree.real_leaf_count
        for leaf_ordinal in range(tree.real_leaf_count):
            fragments = proof_fragments(tree, leaf_ordinal)
            proofs.extend(fragments)
            if verify_proof(tree.leaves[leaf_ordinal], fragments, tree.root):
                verified += 1

    parent_hashes = len(trees) * (TREE_LEAVES - 1)
    parent_compression_blocks = parent_hashes * 2
    parent_sha_rounds = parent_compression_blocks * 64

    fingerprint_payload = {
        "protocol": PROTOCOL,
        "pad_leaf_hex": PAD_LEAF.hex(),
        "digest_counts_by_sequence": digest_counts_by_sequence,
        "tree_counts_by_sequence": tree_counts_by_sequence,
        "roots": roots,
        "proofs": proofs,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    return {
        "protocol": PROTOCOL,
        "pad_leaf_hex": PAD_LEAF.hex(),
        "source_sequences": len(seq_counts),
        "real_leaves": real_leaves,
        "tree_count": len(trees),
        "padding_leaves": padding_leaves,
        "parent_hashes": parent_hashes,
        "parent_compression_blocks": parent_compression_blocks,
        "parent_sha_rounds": parent_sha_rounds,
        "proof_fragments": len(proofs),
        "verified_real_leaf_proofs": verified,
        "digest_counts_by_sequence": digest_counts_by_sequence,
        "tree_counts_by_sequence": tree_counts_by_sequence,
        "oracle_fingerprint": fingerprint,
    }


def main() -> None:
    print(json.dumps(derive_oracle(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
