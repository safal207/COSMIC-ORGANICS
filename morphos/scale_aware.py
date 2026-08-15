"""MORPHOS-S1 scale-aware coupling law.

The law is algorithmic. It is not a calibrated physical scaling law.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from morphos.grid2d import Grid2DConfig

@dataclass(frozen=True)
class ScaleLaw:
    reference_linear_size: float = 5.0
    exponent: float = 0.25
    def __post_init__(self) -> None:
        if self.reference_linear_size <= 0:
            raise ValueError("reference_linear_size must be positive")
        if self.exponent < 0:
            raise ValueError("exponent must be non-negative")
    def factor(self, width: int, height: int) -> float:
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        linear_size = float(max(width, height))
        return (self.reference_linear_size / linear_size) ** self.exponent
    def apply(self, base: Grid2DConfig, *, width: int, height: int) -> Grid2DConfig:
        factor = self.factor(width, height)
        return replace(
            base,
            width=width,
            height=height,
            anchor_coupling=base.anchor_coupling * factor,
            adaptive_coupling=base.adaptive_coupling * factor,
        )
