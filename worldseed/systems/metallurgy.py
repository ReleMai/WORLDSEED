from __future__ import annotations

from dataclasses import dataclass

from worldseed.content.registry import ContentRegistry, RecipeDef
from worldseed.core.rng import PCG32, derive_seed
from worldseed.entities.components import Inventory
from worldseed.systems.state import LivingWorldState, MetalBatchState


@dataclass(slots=True)
class MetallurgyResult:
    quality_hint: int | None = None
    material: str | None = None
    notes: list[str] | None = None


class MetallurgySystem:
    """Persisted metal process state layered onto stack inventory counts.

    Inventory still records commodity counts for compatibility. Every metal unit that has
    been smelted/treated locally may additionally carry a MetalBatchState. Legacy or traded
    metal without metadata is treated as a generic 50-quality batch when consumed.
    """

    METAL_ITEMS = {"core:iron_bloom", "core:steel_billet", "core:copper_ingot"}

    def __init__(self, state: LivingWorldState, registry: ContentRegistry, seed: bytes) -> None:
        self.state = state
        self.registry = registry
        self.seed = seed

    def batches(self, owner: str = "player", item_id: str | None = None) -> list[MetalBatchState]:
        rows = [b for b in self.state.metal_batches.values() if b.owner == owner and (item_id is None or b.item_id == item_id)]
        return sorted(rows, key=lambda b: (b.quality, b.uid), reverse=True)

    def can_process(self, recipe: RecipeDef, inv: Inventory, owner: str = "player") -> tuple[bool, str]:
        for iid, n in recipe.catalysts.items():
            if inv.count(iid) < n:
                return False, f"Requires catalyst: {self.registry.items[iid].name} x{n}."
        if recipe.process in {"normalize_steel", "quench_steel", "temper_steel"}:
            if inv.count("core:steel_billet") <= 0:
                return False, "You need a steel billet."
            batch = self._peek_or_generic("core:steel_billet", owner)
            if recipe.process == "quench_steel" and batch.temperature_c < 700:
                return False, "The steel must be above 700 C before quenching. Re-normalize or freshly carburize it first."
            if recipe.process == "temper_steel" and "quenched" not in batch.treatments:
                return False, "The billet must be quenched before tempering."
        return True, ""

    def apply(self, recipe: RecipeDef, owner: str, minute: int, *, consumed_inputs: dict[str, int] | None = None) -> MetallurgyResult:
        process = recipe.process
        if not process:
            self.consume_inputs(consumed_inputs or recipe.inputs, owner)
            return MetallurgyResult()
        if process == "smelt_copper":
            rng = PCG32(derive_seed(self.seed, "smelt-copper", minute, len(self.state.metal_batches)))
            purity = 58 + rng.randbelow(31)
            quality = max(28, min(88, (purity * 3 + 100) // 4))
            self._create_batch("core:copper_ingot", owner, "core:copper", 1800, 1085, 0, purity, quality, minute, ["copper smelt"], minute+recipe.minutes)
            return MetallurgyResult(quality, "core:copper", [f"purity {purity}"])
        if process == "smelt_iron":
            rng = PCG32(derive_seed(self.seed, "smelt-iron", minute, len(self.state.metal_batches)))
            purity = 55 + rng.randbelow(31)
            carbon = 1 + rng.randbelow(5)
            quality = max(25, min(82, (purity * 3 + 100 - abs(carbon - 3) * 5) // 4))
            self._create_batch("core:iron_bloom", owner, "core:iron", 2000, 1180, carbon, purity, quality, minute, ["bloomery smelt"], minute+recipe.minutes)
            return MetallurgyResult(quality, "core:iron", [f"purity {purity}", f"carbon {carbon/10:.1f}%"])
        if process == "carburize_steel":
            src = self._take_batch("core:iron_bloom", owner)
            rng = PCG32(derive_seed(self.seed, "carburize", minute, src.uid, src.quality))
            carbon = 6 + rng.randbelow(8)
            purity = max(40, min(98, src.purity + 3 - rng.randbelow(5)))
            carbon_fit = max(0, 100 - abs(carbon - 9) * 10)
            quality = max(30, min(92, (src.quality * 2 + purity + carbon_fit) // 4))
            self._create_batch("core:steel_billet", owner, "core:steel", 1800, 1120, carbon, purity, quality, minute, [*src.treatments, "carburized"], minute+recipe.minutes)
            return MetallurgyResult(quality, "core:steel", [f"carbon {carbon/10:.1f}%", f"purity {purity}"])
        if process in {"normalize_steel", "quench_steel", "temper_steel"}:
            batch = self._take_batch("core:steel_billet", owner)
            if process == "normalize_steel":
                batch.temperature_c = 900
                batch.heat_until_minute = minute+recipe.minutes
                batch.quality = min(96, batch.quality + 4)
                batch.purity = min(99, batch.purity + 1)
                batch.treatments.append("normalized")
            elif process == "quench_steel":
                batch.temperature_c = 80
                batch.heat_until_minute = minute
                carbon_fit = max(0, 100 - abs(batch.carbon_permille - 9) * 12)
                batch.quality = max(20, min(98, batch.quality + carbon_fit // 18 - 2))
                batch.treatments.append("quenched")
            elif process == "temper_steel":
                batch.temperature_c = 230
                batch.heat_until_minute = minute+recipe.minutes
                batch.quality = min(99, batch.quality + 6)
                batch.treatments.append("tempered")
            self.state.metal_batches[batch.uid] = batch
            return MetallurgyResult(batch.quality, batch.material, list(batch.treatments))
        if process == "forge_metal_item":
            costs = consumed_inputs if consumed_inputs is not None else recipe.inputs
            batches = self.consume_inputs(costs, owner)
            if not batches:
                return MetallurgyResult(notes=["forged from recovered parts"])
            mass = sum(batch.mass_g for batch in batches)
            quality = sum(batch.quality * batch.mass_g for batch in batches) // max(1, mass)
            dominant = max(batches, key=lambda batch: (batch.mass_g, batch.item_id))
            notes = list(dict.fromkeys(note for batch in batches for note in batch.treatments))
            notes.append(f"forged at {min(batch.temperature_c for batch in batches)}C")
            return MetallurgyResult(quality, dominant.material, notes)
        return MetallurgyResult()


    def consume_inputs(self, costs: dict[str, int], owner: str = 'player') -> list[MetalBatchState]:
        """Retire batch metadata beside already-spent physical metal stock."""
        return [self._take_batch(iid, owner) for iid, count in sorted(costs.items())
                if iid in self.METAL_ITEMS for _ in range(count)]


    def consume_component_input(self, item_id: str, owner: str = "player") -> MetallurgyResult:
        """Consume metadata for one already-removed component commodity.

        Inventory quantities are consumed by the crafting layer; this consumes only the
        corresponding process metadata so a selected steel component carries its actual heat
        treatment/quality into the finished object.
        """
        if item_id not in self.METAL_ITEMS:
            item=self.registry.items.get(item_id);mat=item.material if item else None
            if mat and mat in self.registry.materials:
                m=self.registry.materials[mat];q=max(20,min(85,(m.hardness+m.toughness+m.edge)//3))
                return MetallurgyResult(q,mat,["commodity component"])
            return MetallurgyResult(50,mat,["generic component"])
        batch=self._take_batch(item_id,owner)
        return MetallurgyResult(batch.quality,batch.material,list(batch.treatments))

    def cool_hourly(self, current_minute: int, hours: int = 1) -> None:
        if hours <= 0:
            return
        for batch in self.state.metal_batches.values():
            if current_minute <= batch.heat_until_minute:continue
            if batch.temperature_c > 25:
                batch.temperature_c = max(25, batch.temperature_c - 260 * hours)

    def transfer_one(self, item_id: str, from_owner: str, to_owner: str, minute: int) -> None:
        if item_id not in self.METAL_ITEMS:
            return
        candidates = self.batches(from_owner, item_id)
        if candidates:
            candidates[-1].owner = to_owner
            return
        # Aggregate markets do not preserve every billet. Materialize representative quality
        # deterministically only when a player acquires one.
        if to_owner == "player":
            if item_id == "core:steel_billet":
                self._create_batch(item_id, to_owner, "core:steel", 1800, 25, 8, 72, 58, minute, ["market stock"])
            elif item_id == "core:copper_ingot":
                self._create_batch(item_id, to_owner, "core:copper", 1800, 25, 0, 72, 56, minute, ["market stock"])
            else:
                self._create_batch(item_id, to_owner, "core:iron", 2000, 25, 3, 68, 52, minute, ["market stock"])

    def describe_owner_batches(self, owner: str = "player") -> list[str]:
        out = []
        for b in self.batches(owner):
            out.append(
                f"{self.registry.items[b.item_id].name}: q{b.quality} {b.temperature_c}C "
                f"carbon {b.carbon_permille/10:.1f}% purity {b.purity}% [{', '.join(b.treatments[-3:])}]"
            )
        return out

    def _create_batch(self, item_id: str, owner: str, material: str, mass_g: int, temperature: int,
                      carbon: int, purity: int, quality: int, minute: int, treatments: list[str], heat_until_minute: int | None = None) -> MetalBatchState:
        uid = self.state.uid("metal")
        batch = MetalBatchState(uid, item_id, owner, material, mass_g, temperature, carbon, purity, quality, minute, minute if heat_until_minute is None else heat_until_minute, treatments)
        self.state.metal_batches[uid] = batch
        return batch

    def _peek_or_generic(self, item_id: str, owner: str) -> MetalBatchState:
        rows = self.batches(owner, item_id)
        if rows:
            return rows[-1]
        material = "core:steel" if item_id == "core:steel_billet" else "core:copper" if item_id == "core:copper_ingot" else "core:iron"
        mass = 1800 if item_id in {"core:steel_billet", "core:copper_ingot"} else 2000
        carbon = 8 if item_id == "core:steel_billet" else 0 if item_id == "core:copper_ingot" else 3
        return MetalBatchState("generic", item_id, owner, material, mass, 25, carbon, 65, 50, 0, 0, ["legacy/generic"])

    def _take_batch(self, item_id: str, owner: str) -> MetalBatchState:
        rows = self.batches(owner, item_id)
        if rows:
            batch = rows[-1]
            self.state.metal_batches.pop(batch.uid, None)
            return batch
        return self._peek_or_generic(item_id, owner)
