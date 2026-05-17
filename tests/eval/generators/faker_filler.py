"""Deterministic slot realisation for multi-turn eval templates.

A template declares slots (`Faker` calls or `choices` lists) and references
them in turn text with `{slot_name}` placeholders. Each *session* gets a
stable integer seed → reproducible Faker outputs → ground-truth that the
leak runner can compare against by literal substring match.

The filler is deliberately Faker-only — no model is in the realisation loop,
so ground truth never depends on GPT moods.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml
from faker import Faker


@dataclass(frozen=True)
class Turn:
    role: str  # "user" | "assistant"
    text: str


@dataclass(frozen=True)
class EntityValue:
    slot: str
    type: str
    value: str


@dataclass(frozen=True)
class Session:
    template_id: str
    seed: int
    turns: list[Turn] = field(default_factory=list)
    entities: list[EntityValue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "seed": self.seed,
            "turns": [asdict(t) for t in self.turns],
            "entities": [asdict(e) for e in self.entities],
        }


def _realize_slot(spec: dict[str, Any], faker: Faker) -> str:
    """Turn one slot spec into a concrete string."""
    if "choices" in spec:
        return str(faker.random_element(spec["choices"]))
    fn_name = spec.get("faker")
    if not fn_name:
        raise ValueError(f"slot needs 'choices' or 'faker': {spec!r}")
    fn = getattr(faker, fn_name, None)
    if fn is None:
        raise ValueError(f"unknown faker provider: {fn_name!r}")
    value = fn(**spec.get("args", {}))
    fmt = spec.get("format")
    if fmt and hasattr(value, "strftime"):
        return value.strftime(fmt)
    # Address (and a few others) are multi-line by default. Collapse to a
    # single line so detection doesn't see surprise paragraph breaks.
    return str(value).replace("\n", ", ")


def fill_template(template: dict[str, Any], seed: int, *, locale: str = "en_US") -> Session:
    faker = Faker(locale)
    faker.seed_instance(seed)

    slot_values: dict[str, str] = {}
    entities: list[EntityValue] = []
    for slot_name, spec in template.get("slots", {}).items():
        v = _realize_slot(spec, faker)
        slot_values[slot_name] = v
        entities.append(EntityValue(slot=slot_name, type=spec["type"], value=v))

    turns: list[Turn] = []
    for t in template["turns"]:
        try:
            text = t["text"].format(**slot_values)
        except KeyError as e:
            raise ValueError(
                f"template {template['id']!r}: turn references missing slot {e}"
            ) from None
        # Collapse the YAML folded-scalar whitespace so leak detection sees
        # normalized prose.
        text = " ".join(text.split())
        turns.append(Turn(role=t["role"], text=text))

    return Session(
        template_id=template["id"],
        seed=seed,
        turns=turns,
        entities=entities,
    )


def load_template(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f)


def realize_paraphrased_session(
    template: dict[str, Any],
    variant: dict[str, Any],
    seed: int,
    *,
    locale: str = "en_US",
) -> Session:
    """Realise a paraphrased variant using the original template's slot specs.

    ``variant`` has the same slot tokens as ``template`` but different
    natural-language turn text (and possibly slots moved across turns).
    Slot specs (faker calls, choices, formats) always come from the
    original template — variants only carry prose.
    """
    synthetic = {
        **template,
        "id": variant.get("id", template["id"]),
        "turns": variant["turns"],
    }
    return fill_template(synthetic, seed, locale=locale)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[42, 137, 256, 1024],
        help="One or more integer seeds (each yields one session).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable preview.",
    )
    args = parser.parse_args()

    template = load_template(args.template)
    sessions = [fill_template(template, seed) for seed in args.seeds]

    if args.json:
        print(json.dumps([s.to_dict() for s in sessions], indent=2, ensure_ascii=False))
        return

    for sess in sessions:
        print(f"\n=== {sess.template_id} | seed={sess.seed} ===")
        for t in sess.turns:
            print(f"[{t.role:9}] {t.text}")
        print("  entities:")
        for e in sess.entities:
            print(f"    {e.slot:14} {e.type:10} → {e.value!r}")


if __name__ == "__main__":
    main()
