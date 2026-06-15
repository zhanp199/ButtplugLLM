"""Vibration pattern templates: model, presets, and JSON persistence.

A pattern is an ordered list of steps; each step holds an intensity (0.0-1.0)
and a duration in ms. ``loop`` repeats the whole step sequence: 0 = play once,
N = play N+1 times total. Templates are stored on the MCP-server side so the LLM
and the manual UI share one source of truth.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Step:
    intensity: float
    duration_ms: int

    def clamped(self, max_intensity: float, max_duration_ms: int) -> "Step":
        return Step(
            intensity=max(0.0, min(max_intensity, float(self.intensity))),
            duration_ms=max(0, min(max_duration_ms, int(self.duration_ms))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"intensity": self.intensity, "duration_ms": self.duration_ms}


@dataclass
class Pattern:
    name: str
    steps: list[Step] = field(default_factory=list)
    loop: int = 0  # number of *extra* repeats; 0 = play once

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps],
            "loop": self.loop,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Pattern":
        steps = [
            Step(intensity=float(s["intensity"]), duration_ms=int(s["duration_ms"]))
            for s in d.get("steps", [])
        ]
        return Pattern(name=str(d["name"]), steps=steps, loop=int(d.get("loop", 0)))

    def total_ms(self) -> int:
        return sum(s.duration_ms for s in self.steps) * (self.loop + 1)


def pulse_pattern(
    frequency_hz: float,
    intensity: float = 1.0,
    total_ms: int = 5000,
    duty: float = 0.5,
    name: str = "pulse",
) -> Pattern:
    """Build an on/off pulse train at a given frequency.

    ``frequency_hz`` is pulses per second; ``duty`` is the fraction of each cycle
    spent "on". Used by the UI frequency slider and the ``pulse`` preset.
    """
    frequency_hz = max(0.1, min(20.0, float(frequency_hz)))
    duty = max(0.05, min(0.95, float(duty)))
    period_ms = 1000.0 / frequency_hz
    on_ms = max(1, round(period_ms * duty))
    off_ms = max(1, round(period_ms * (1 - duty)))
    one_cycle = on_ms + off_ms
    cycles = max(1, round(total_ms / one_cycle))
    steps: list[Step] = []
    for _ in range(cycles):
        steps.append(Step(intensity=intensity, duration_ms=on_ms))
        steps.append(Step(intensity=0.0, duration_ms=off_ms))
    return Pattern(name=name, steps=steps, loop=0)


def default_presets() -> list[Pattern]:
    """Pleasure-focused presets, designed to build over a minute or more.

    These seed templates.json on first run; after that, edit templates.json
    directly (the UI no longer adds/removes templates).
    """
    return [
        Pattern(name="暖身 Warm-Up", loop=0, steps=[
            Step(0.12, 8000), Step(0.20, 10000), Step(0.30, 12000),
            Step(0.42, 14000), Step(0.55, 16000),
        ]),
        Pattern(name="挑逗 Tease", loop=7, steps=[
            Step(0.60, 800), Step(0.0, 1200), Step(0.75, 600), Step(0.0, 1500),
            Step(0.50, 1000), Step(0.0, 2000), Step(0.85, 700), Step(0.0, 1300),
        ]),
        Pattern(name="海浪 Waves", loop=5, steps=[
            Step(0.30, 2000), Step(0.50, 2000), Step(0.70, 2000),
            Step(0.92, 2500), Step(0.70, 2000), Step(0.50, 2000),
        ]),
        Pattern(name="心跳 Racing Heart", loop=70, steps=[
            Step(0.95, 140), Step(0.30, 100), Step(0.95, 140), Step(0.30, 450),
        ]),
        Pattern(name="边缘 Edge", loop=2, steps=[
            Step(0.40, 5000), Step(0.60, 6000), Step(0.80, 7000),
            Step(0.95, 9000), Step(0.10, 5000),
        ]),
        Pattern(name="榨取 Milking", loop=6, steps=[
            Step(0.70, 3000), Step(0.90, 2000), Step(0.70, 3000), Step(1.00, 2500),
        ]),
        Pattern(name="失控 Overload", loop=2, steps=[
            Step(1.00, 6000), Step(0.60, 1500), Step(1.00, 6000),
            Step(0.70, 1500), Step(1.00, 8000),
        ]),
        Pattern(name="高潮 Climax", loop=0, steps=[
            Step(0.50, 5000), Step(0.65, 6000), Step(0.80, 8000),
            Step(0.90, 10000), Step(1.00, 25000), Step(1.00, 20000),
        ]),
        Pattern(name="余韵 Afterglow", loop=0, steps=[
            Step(0.50, 8000), Step(0.35, 10000), Step(0.25, 12000),
            Step(0.15, 12000), Step(0.08, 10000),
        ]),
    ]


class TemplateStore:
    """Loads / saves named patterns to a JSON file. Seeds presets on first run."""

    def __init__(self, path: str):
        self.path = path
        self._patterns: dict[str, Pattern] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._patterns = {
                    d["name"]: Pattern.from_dict(d) for d in data.get("patterns", [])
                }
                return
            except (json.JSONDecodeError, KeyError, OSError):
                pass  # fall through to presets
        for p in default_presets():
            self._patterns[p.name] = p
        self._save()

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"patterns": [p.to_dict() for p in self._patterns.values()]},
                f,
                indent=2,
            )
        os.replace(tmp, self.path)

    def list(self) -> list[Pattern]:
        return list(self._patterns.values())

    def get(self, name: str) -> Pattern | None:
        return self._patterns.get(name)

    def add(self, pattern: Pattern) -> None:
        self._patterns[pattern.name] = pattern
        self._save()

    def delete(self, name: str) -> bool:
        if name in self._patterns:
            del self._patterns[name]
            self._save()
            return True
        return False
