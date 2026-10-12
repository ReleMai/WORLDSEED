"""Deterministic dismantling of carried objects into catalog crafting parts.

The input is spent when work begins, so leaving the menu or loading a save
cannot reroll it. Inspection and three decisions preserve an active project;
only its final decision creates outputs and grants practice.
"""
from __future__ import annotations

from copy import deepcopy

from worldseed.content.registry import ContentRegistry, SalvageDef
from worldseed.core.rng import hash_u64
from worldseed.entities.components import Inventory
from worldseed.persistence.validation import validate_salvage_session
from worldseed.systems.state import LivingWorldState
from worldseed.systems import salvage_games, salvage_perks

SALVAGE_PROTOCOL_VERSION = 1
SALVAGE_LOG_LIMIT = 80

_METHODS = {
    "unfasten": ("Unfasten joints", "Unscrew and ease the fitted fasteners free.", "Fitted fasteners can be unscrewed; prying tears their threads."),
    "strip": ("Strip layers", "Peel or unwind the layers along their seams.", "Layered material should be peeled along its seams to preserve fibers."),
    "sort": ("Sort pieces", "Separate the mixed loose pieces by material.", "Loose mixed pieces need sorting; cutting or grinding loses intact parts."),
    "crush": ("Crush carefully", "Break the brittle body into usable graded fragments.", "A brittle body has no reusable joints; controlled crushing recovers its fragments."),
    "carve": ("Carve along grain", "Split and pare along the grain with light cuts.", "The grain marks clean cuts; splitting across it splinters the useful wood or bone."),
    "clean": ("Clean and separate", "Brush away debris and separate the natural parts.", "Natural parts are fouled by debris; careful cleaning preserves their useful surfaces."),
}


class SalvagingSystem:
    def __init__(self, state: LivingWorldState, registry: ContentRegistry) -> None:
        self.state = state
        self.registry = registry

    def _level(self) -> int:
        return max(0, min(10, int(self.state.player_skills.get("salvaging", 0))))

    @staticmethod
    def skill_threshold(level: int) -> int:
        # The same increasing practice-threshold contract as fishing.
        return 24 + max(0, min(10, level)) * 14

    def _best_quality(self, inv: Inventory, quality: str, source: str = "") -> int:
        return max((item.quality(quality) for iid, n in inv.items.items()
                    if n > (1 if iid == source else 0)
                    and (item := self.registry.items.get(iid)) is not None), default=0)

    def can_start(self, item_id: str, inv: Inventory) -> tuple[bool, str]:
        if not isinstance(item_id, str) or item_id not in self.registry.salvage:
            return False, "That item has no salvageable components."
        if self.state.player_salvage_session:
            return False, "Finish your current salvage project first."
        if inv.count(item_id) <= 0:
            return False, "You do not carry that item."
        if item_id in self.state.player_equipment.values():
            return False, "Unequip that item before salvaging it."
        if item_id == self.state.player_readied_weapon:
            return False, "Lower your readied weapon before salvaging it."
        definition = self.registry.salvage[item_id]
        for quality, need in definition.tool_qualities.items():
            have = self._best_quality(inv, quality, item_id)
            if have < need:
                return False, f"Requires {quality} quality {need}; your best spare tool is {have}."
        if self.state.salvaging_attempts >= 1_000_000_000:
            return False, "The salvage work ledger is full."
        return True, ""

    def can_quick(self, item_id: str, inv: Inventory) -> tuple[bool, str]:
        """The Makeshift Rig perk relaxes only tools, never ownership/equipment guards."""
        ok, reason = self.can_start(item_id, inv)
        if ok or not salvage_perks.has(self.state, "makeshift_rig"):
            return ok, reason
        definition = self.registry.salvage.get(item_id)
        if (definition is None or self.state.player_salvage_session or inv.count(item_id) <= 0
                or item_id in self.state.player_equipment.values()
                or item_id == self.state.player_readied_weapon
                or self.state.salvaging_attempts >= 1_000_000_000):
            return False, reason
        if all(self._best_quality(inv,quality,item_id) >= max(0,need-1)
               for quality,need in definition.tool_qualities.items()):
            return True, ""
        return False, reason

    def preview(self, item_id: str, inv: Inventory | None = None) -> dict | None:
        """An observational preview; no dice, discovery or reservation is made."""
        if not isinstance(item_id, str):
            return None
        definition = self.registry.salvage.get(item_id)
        if definition is None:
            return None
        ok, reason = self.can_start(item_id, inv) if inv is not None else (True, "")
        quick_ok, quick_reason = self.can_quick(item_id, inv) if inv is not None else (True, "")
        level = self._level()
        return {
            "item_id": item_id, "name": self.registry.items[item_id].name,
            "method": definition.method, "description": definition.description,
            "minutes": definition.minutes, "difficulty": definition.difficulty,
            "tools": dict(definition.tool_qualities), "can_start": ok, "reason": reason,
            "quick_can_start": quick_ok, "quick_reason": quick_reason,
            "guaranteed": [{"item_id": iid, "name": self.registry.items[iid].name,
                            "min": low, "max": high} for iid, (low, high) in sorted(definition.yields.items())],
            "rare": [{"item_id": drop.item_id, "name": self.registry.items[drop.item_id].name,
                      "min": drop.min, "max": drop.max, "chance_percent": drop.chance_percent}
                     for drop in definition.rare_yields],
            "skill_level": level, "skill_xp": self.state.player_salvaging_xp,
            "skill_threshold": self.skill_threshold(level),
        }

    def available_items(self, inv: Inventory) -> list[dict]:
        rows = []
        for item_id, count in inv.items.items():
            if count > 0 and item_id in self.registry.salvage:
                ok, reason = self.can_start(item_id, inv)
                rows.append({"item_id": item_id, "name": self.registry.items[item_id].name,
                             "count": count, "can_start": ok, "reason": reason})
        return sorted(rows, key=lambda row: (row["name"].casefold(), row["item_id"]))

    def begin(self, item_id: str, inv: Inventory, world_seed: bytes, minute: int = 0) -> tuple[bool, str, int]:
        ok, reason = self.can_start(item_id, inv)
        if not ok:
            return False, reason, 0
        definition = self.registry.salvage[item_id]
        attempt = self.state.salvaging_attempts
        level = self._level()
        tool_bonus = min(12, sum(self._best_quality(inv, key, item_id)
                                for key in ("salvage", "cut", "hammer", "fasten")))
        challenges = [hash_u64(world_seed, "salvaging.challenges.v1", attempt, item_id, index) % 3
                      for index in range(3)]
        # All validation and random keys are resolved before consuming the input.
        if not inv.remove(item_id, 1):
            return False, "You no longer carry that item.", 0
        from worldseed.systems.crafting_quality import retire_consumed_artifacts
        retire_consumed_artifacts(self.state,self.registry,{item_id:1},minute=minute,reason='Set aside for salvage')
        self.state.salvaging_attempts = attempt + 1
        self.state.player_salvage_session = {
            "version": SALVAGE_PROTOCOL_VERSION, "item_id": item_id,
            "definition_id": definition.id, "attempt": attempt,
            "started_minute": minute, "phase": "inspection", "step": 0,
            "score": 0, "choices": [], "challenges": challenges,
            "skill_level": level, "tool_bonus": tool_bonus,
            "dial":(challenges[0]+4)%5,"precision":0,"dial_moves":0,
        }
        return True, f"You set aside one {self.registry.items[item_id].name.lower()} for salvaging. Inspect it before disassembly.", 1

    def begin_game(self, item_id: str, inv: Inventory, world_seed: bytes, minute: int = 0) -> tuple[bool, str, int]:
        """Start the detailed tabletop mode; v1 active projects remain resumable."""
        ok, message, duration = self.begin(item_id, inv, world_seed, minute)
        if not ok:
            return ok, message, duration
        old = self.state.player_salvage_session
        definition = self.registry.salvage[item_id]
        self.state.player_salvage_session = salvage_games.create_project(
            definition, item_id, old["attempt"], world_seed, minute,
            old["skill_level"], old["tool_bonus"], self.state)
        return True, f"Set aside {self.registry.items[item_id].name}. {salvage_games.GAME_DESCRIPTIONS[self.state.player_salvage_session['game']]}", duration

    def perk_view(self) -> dict:
        return salvage_perks.view(self.state)

    def buy_perk(self, perk_id: str) -> tuple[bool, str]:
        return salvage_perks.purchase(self.state, perk_id)

    def reset_perks(self) -> tuple[bool, str]:
        return salvage_perks.respec(self.state)

    def quick_batch(self, item_id: str, count: int, inv: Inventory, world_seed: bytes,
                    minute: int = 0) -> tuple[bool, str, int]:
        """Repeated authorized quick jobs, with a deterministic batch time discount."""
        count = int(count) if type(count) is int else 0
        limit = 6 if salvage_perks.has(self.state, 'wreckbreaker') else 4 if salvage_perks.has(self.state, 'sweep_job') else 1
        if count < 1 or count > limit or inv.count(item_id) < count:
            return False, f"Select between one and {limit} carried copies.", 0
        shadow=Inventory(dict(inv.items))
        for _ in range(count):
            ok, reason = self.can_quick(item_id, shadow)
            if not ok:
                return False, reason, 0
            shadow.remove(item_id, 1)
        total, completed = 0, 0
        for index in range(count):
            ok, reason, duration = self.quick(item_id, inv, world_seed, minute + total)
            if not ok:
                break
            total += duration
            completed += 1
        if completed == 0:
            return False, reason, 0
        if completed > 1:
            total = max(completed * 2, total - (completed - 1) * 2)
        return True, f"Quick-salvaged {completed} items. Recovery reports are in your log.", total

    def claim_dossier(self, station_id: str, nearby_stations: set[str]) -> tuple[bool, str]:
        """Spend completed research only while physically at its workshop."""
        if not salvage_perks.has(self.state, "lost_arts"):
            return False, "Unlock Lost Arts first."
        if station_id not in nearby_stations:
            return False, "You must stand at this physical workshop to research the dossier."
        sources = self.state.player_salvage_dossiers.get(station_id, [])
        if len(sources) < 3:
            return False, "Salvage three distinct pristine sources to finish this dossier."
        candidates = sorted((recipe for recipe in self.registry.recipes.values()
                             if recipe.station == station_id
                             and recipe.id not in self.state.player_discovered_recipes
                             and (not recipe.knowledge or recipe.knowledge in self.state.player_knowledge)),
                            key=lambda recipe: recipe.id)
        if not candidates:
            return False, "No eligible undiscovered designs remain for this workshop."
        recipe = candidates[0]
        self.state.player_discovered_recipes = sorted(set(self.state.player_discovered_recipes) | {recipe.id})
        self.state.player_unseen_recipes = sorted(set(self.state.player_unseen_recipes) | {recipe.id})
        self.state.player_salvage_dossiers[station_id] = []
        return True, f"The {self.registry.structures[station_id].name if station_id in self.registry.structures else 'workshop'} dossier reveals {recipe.name}."

    def _finish_game(self, session: dict, definition: SalvageDef, inv: Inventory,
                     world_seed: bytes, minute: int, duration: int) -> tuple[bool, str, int]:
        quality = salvage_games.quality(session)
        level = session["skill_level"]
        score = max(0, min(6, (quality * 6 + 50) // 100))
        outputs = self.roll_outputs(definition.item_id, score, level,
                                    world_seed, session["attempt"], session["tool_bonus"])
        rare_ids = {drop.item_id for drop in definition.rare_yields}
        perks = salvage_perks.owned(self.state)
        if quality >= 70 and "intact_recovery" in perks and definition.yields:
            first = sorted(definition.yields)[0]
            outputs[first] = outputs.get(first, 0) + 1
        priority = session.get("priority", "")
        if "targeted_search" in perks and priority:
            if priority in definition.yields:
                outputs[priority] = outputs.get(priority, 0) + 1
            else:
                for drop in definition.rare_yields:
                    if drop.item_id != priority:
                        continue
                    chance = self._rare_chance(drop.chance_percent, score, level,
                                               session["tool_bonus"], definition.difficulty)
                    roll = hash_u64(world_seed, "salvaging.rare.v1", session["attempt"],
                                    definition.item_id, drop.item_id) % 100
                    if roll < min(100, chance + 10) and priority not in outputs:
                        outputs[priority] = drop.min
        if quality == 100 and "conservator" in perks:
            if definition.rare_yields:
                first = sorted(definition.rare_yields, key=lambda entry: entry.item_id)[0]
                outputs.setdefault(first.item_id, first.min)
            elif definition.yields:
                first = sorted(definition.yields)[0]
                outputs[first] = outputs.get(first, 0) + 1
        for iid, amount in outputs.items():
            inv.add(iid, amount)
        prior_sources = {row.get('item_id') for row in self.state.player_salvage_log}
        messages = []
        if "workshop_whisper" in perks or ("notes_from_ruins" in perks and definition.item_id not in prior_sources):
            for iid in sorted(outputs):
                matched = next((recipe for recipe in sorted(self.registry.recipes.values(), key=lambda r: r.id)
                                if recipe.station and iid in recipe.inputs
                                and recipe.id not in self.state.player_discovered_recipes), None)
                if matched:
                    existing = {h.get("recipe_id") for h in self.state.player_crafting_hints}
                    if matched.id not in existing:
                        self.state.player_crafting_hints.append({"recipe_id": matched.id, "station_id": matched.station, "item_id": iid})
                        self.state.player_crafting_hints = self.state.player_crafting_hints[-200:]
                        station = self.registry.structures.get(matched.station)
                        messages.append("Workshop hint: " + (station.name if station else matched.station))
                    break
        if "notes_from_ruins" in perks and definition.item_id not in prior_sources:
            messages.append("Field notes: " + definition.description)
        if quality == 100 and "lost_arts" in perks:
            for station in sorted({recipe.station for recipe in self.registry.recipes.values()
                                    if recipe.station and any(iid in recipe.inputs for iid in outputs)}):
                rows = self.state.player_salvage_dossiers.setdefault(station, [])
                if definition.item_id not in rows and len(rows) < 3:
                    rows.append(definition.item_id)
                    if len(rows) == 3:
                        messages.append("Completed a workshop research dossier.")
                break
        gain = self._practice(score, definition.difficulty)
        names = ", ".join(f"{self.registry.items[iid].name} x{amount}"
                          for iid, amount in sorted(outputs.items()))
        message = f"Salvaged {self.registry.items[definition.item_id].name}: {names}. Quality {quality}/100; practice +{gain}."
        if messages:
            message += " " + " ".join(messages)
        self.state.player_salvage_log.append({
            "item_id": definition.item_id, "name": self.registry.items[definition.item_id].name,
            "attempt": session["attempt"], "completed_minute": minute + duration,
            "score": quality, "max_score": 100, "outputs": dict(outputs),
            "rare_outputs": {iid: amount for iid, amount in outputs.items() if iid in rare_ids},
            "skill_level": self._level(), "skill_xp": self.state.player_salvaging_xp,
            "xp_gained": gain, "method": session["game"], "message": message,
        })
        del self.state.player_salvage_log[:-SALVAGE_LOG_LIMIT]
        self.state.player_salvage_session = {}
        return True, message, duration

    def _stage(self, session: dict, definition: SalvageDef) -> dict:
        index = session["step"]
        challenge = session["challenges"][index]
        if index == 0:
            cues = (
                "Loose joints rattle. Brace the assembly so parts cannot twist or scatter.",
                "Thin edges chip easily. Pad the fragile surfaces before applying pressure.",
                "Dirt hides the joins. Brush the seams clean before pulling pieces apart.",
            )
            choices = [("brace", "Brace assembly", "Hold loose joints steady."),
                       ("pad", "Pad fragile edges", "Cushion surfaces that might chip."),
                       ("brush", "Brush seams", "Clear grit and reveal hidden joins.")]
            correct = ("brace", "pad", "brush")[challenge]
            prompt, cue = "Prepare the object", cues[challenge]
        elif index == 1:
            alternatives = {
                "unfasten": ("carve", "crush"), "strip": ("clean", "crush"),
                "sort": ("clean", "crush"), "crush": ("sort", "unfasten"),
                "carve": ("strip", "crush"), "clean": ("strip", "crush"),
            }
            ids = (definition.method, *alternatives[definition.method])
            choices = [(key, _METHODS[key][0], _METHODS[key][1]) for key in ids]
            # Rotate presentation order without changing which action preserves parts.
            choices = choices[challenge:] + choices[:challenge]
            correct = definition.method
            prompt, cue = "Disassemble the material", _METHODS[definition.method][2]
        else:
            cues = (
                "The recovered pieces are mixed together. Sort intact parts away from scraps.",
                "The recovered surfaces still carry grit. Clean them before storing the parts.",
                "A delicate inner component is exposed. Lift it free before collecting scraps.",
            )
            choices = [("sort_parts", "Sort intact parts", "Separate reusable pieces by material."),
                       ("clean_parts", "Clean recovered parts", "Brush grit off reusable surfaces."),
                       ("lift_core", "Lift delicate core", "Release the inner component without bending it.")]
            correct = ("sort_parts", "clean_parts", "lift_core")[challenge]
            prompt, cue = "Recover useful parts", cues[challenge]
        return {"prompt": prompt, "cue": cue, "correct": correct,
                "choices": [{"id": key, "label": label, "description": description}
                            for key, label, description in choices]}

    def session_view(self) -> dict | None:
        session = self.state.player_salvage_session
        if not session:
            return None
        if validate_salvage_session(session, self.state.salvaging_attempts):
            return None
        definition = self.registry.salvage.get(session.get("item_id"))
        if definition is None:
            return None
        if session.get("version") == 2:
            return salvage_games.view(session, self.registry.items[definition.item_id].name,
                                      self.state, definition)
        view = {"item_id": definition.item_id, "name": self.registry.items[definition.item_id].name,
                "phase": session["phase"], "step": session["step"], "stage_count": 3,
                "score": session["score"], "max_score": 6,
                "precision":session.get("precision",0),
                "dial":session.get("dial",(session["challenges"][session["step"]]+4)%5),
                "target":(session["challenges"][session["step"]]*2+1)%5}
        if session["phase"] == "inspection":
            view.update(prompt="Inspect the assembly", cue=definition.description,
                        choices=[{"id": "inspect", "label": "Inspect assembly",
                                  "description": "Find fragile seams before taking it apart."}])
        else:
            stage = self._stage(session, definition)
            view.update({key: deepcopy(value) for key, value in stage.items() if key != "correct"})
        return view

    @staticmethod
    def _rare_chance(base: int, score: int, level: int, tool_bonus: int, difficulty: int) -> int:
        # The authored percentage is the baseline at four points. Skill and
        # careful work improve it; a failed sequence still cannot remove common parts.
        return max(1, min(100, base + (score - 4) * 2 + level + tool_bonus // 3 - difficulty // 2))

    def roll_outputs(self, item_id: str, score: int, skill_level: int, world_seed: bytes,
                     attempt: int | str, tool_bonus: int = 0) -> dict[str, int]:
        """Shared deterministic yields. NPC callers own consumption and transfers.

        This function is observational: identical source/work identities and
        quality always produce identical drops, even across save reloads.
        """
        definition = self.registry.salvage[item_id]
        score, level = max(0, min(6, score)), max(0, min(10, skill_level))
        efficiency = max(0, min(100, 20 + score * 11 + level * 3 + tool_bonus - definition.difficulty * 3))
        outputs = {}
        for iid, (low, high) in sorted(definition.yields.items()):
            potential = hash_u64(world_seed, "salvaging.common.v1", attempt, item_id, iid) % (high - low + 1)
            whole, remainder = divmod(potential * efficiency, 100)
            # Deterministic fractional recovery keeps quality meaningful even
            # for the common one-to-two-part ranges; it is monotonic in care.
            extra = hash_u64(world_seed, "salvaging.common_fraction.v1", attempt, item_id, iid) % 100 < remainder
            outputs[iid] = low + whole + int(extra)
        for drop in definition.rare_yields:
            chance = self._rare_chance(drop.chance_percent, score, level, tool_bonus, definition.difficulty)
            if hash_u64(world_seed, "salvaging.rare.v1", attempt, item_id, drop.item_id) % 100 < chance:
                outputs[drop.item_id] = drop.min + hash_u64(world_seed, "salvaging.rare_amount.v1", attempt, item_id, drop.item_id) % (drop.max - drop.min + 1)
        return outputs

    def _practice(self, score: int, difficulty: int, *,quick:bool=False) -> int:
        level = self._level()
        if level >= 10:
            return 0
        gain = 1 if quick else 2 + score // 2 + min(2, difficulty // 3)
        self.state.player_salvaging_xp += gain
        threshold = self.skill_threshold(level)
        if self.state.player_salvaging_xp >= threshold:
            self.state.player_salvaging_xp -= threshold
            self.state.player_skills["salvaging"] = level + 1
            if level + 1 in (5, 10):
                self.state.player_salvage_respecs = min(3, self.state.player_salvage_respecs + 1)
        return gain

    def quick(self,item_id:str,inv:Inventory,world_seed:bytes,minute:int=0)->tuple[bool,str,int]:
        """Low-yield, no-rare, minimal-XP alternative to careful salvage."""
        ok,reason=self.can_quick(item_id,inv)
        if not ok:return False,reason,0
        definition=self.registry.salvage[item_id]
        attempt=self.state.salvaging_attempts
        if not inv.remove(item_id,1):return False,"You no longer carry that item.",0
        from worldseed.systems.crafting_quality import retire_consumed_artifacts
        retire_consumed_artifacts(self.state,self.registry,{item_id:1},minute=minute,reason='Quick salvage')
        self.state.salvaging_attempts+=1
        potential=self.roll_outputs(item_id,0,self._level(),world_seed,attempt,0)
        efficiency = 0.85 if salvage_perks.has(self.state,"wreckbreaker") else 0.75 if salvage_perks.has(self.state,"sorted_scrap") else 0.65
        outputs={iid:max(1,min(high,int(potential.get(iid,low)*efficiency)))
                 for iid,(low,high) in definition.yields.items()}
        rare_outputs={}
        if salvage_perks.has(self.state,"wreckbreaker"):
            for drop in definition.rare_yields:
                chance=self._rare_chance(drop.chance_percent,0,self._level(),0,definition.difficulty)
                roll=hash_u64(world_seed,"salvaging.rare.v1",attempt,item_id,drop.item_id)%100
                if roll < max(1,chance//5):
                    rare_outputs[drop.item_id]=drop.min
                    outputs[drop.item_id]=drop.min
        for iid,amount in outputs.items():inv.add(iid,amount)
        gain=self._practice(0,definition.difficulty,quick=True)
        duration=max(4,min(12,(definition.minutes+2)//3))
        if salvage_perks.has(self.state,"fast_hands"):
            duration=max(3,(duration*4+4)//5)
        message=("Quick salvaged "+self.registry.items[item_id].name+": "+
                 ", ".join(f"{self.registry.items[iid].name} x{qty}" for iid,qty in sorted(outputs.items()))+
                 f". Rough recovery, no rare parts; +{gain} practice.")
        self.state.player_salvage_log.append({
            "item_id":item_id,"name":self.registry.items[item_id].name,
            "attempt":attempt,"completed_minute":minute+duration,
            "score":0,"max_score":6,"outputs":dict(outputs),"rare_outputs":rare_outputs,
            "skill_level":self._level(),"skill_xp":self.state.player_salvaging_xp,
            "xp_gained":gain,"method":"quick","message":message,
        })
        del self.state.player_salvage_log[:-SALVAGE_LOG_LIMIT]
        return True,message,duration

    def act(self, choice_id: str, inv: Inventory, world_seed: bytes, minute: int = 0) -> tuple[bool, str, int]:
        session = self.state.player_salvage_session
        if not session:
            return False, "Start a salvage project first.", 0
        if validate_salvage_session(session, self.state.salvaging_attempts):
            return False, "The saved salvage project is invalid; verify the save before resuming.", 0
        definition = self.registry.salvage.get(session.get("item_id"))
        if definition is None or definition.id != session.get("definition_id"):
            return False, "This project's salvage definition is unavailable.", 0
        if not isinstance(choice_id, str):
            return False, "Choose one of the displayed salvage actions.", 0
        if session.get("version") == 2:
            if choice_id.startswith("prioritize:"):
                iid=choice_id.split(":",1)[1]
                if iid not in definition.yields and iid not in {d.item_id for d in definition.rare_yields}:
                    return False,"Select an actual possible recovery output.",0
            ok, message, duration, finished = salvage_games.play(session, choice_id, self.state)
            if not ok:
                return False, message, 0
            if finished:
                return self._finish_game(session, definition, inv, world_seed, minute, duration)
            return True, message, duration
        if session["phase"] == "inspection":
            if choice_id != "inspect":
                return False, "Inspect the assembly before disassembling it.", 0
            session["phase"] = "disassembly"
            return True, "You inspect the seams and identify how to preserve the useful parts.", 1
        stage = self._stage(session, definition)
        if choice_id in ("tune_left","tune_right"):
            if session.get("dial_moves",0)>=6:
                return False,"The mechanism resists further adjustment. Select a technique.",0
            session["dial"]=(session.get("dial",0)+(1 if choice_id=="tune_right" else -1))%5
            session["dial_moves"]=session.get("dial_moves",0)+1
            return True,"Calibration adjusted; match the highlight before choosing a technique.",0
        if choice_id not in {row["id"] for row in stage["choices"]}:
            return False, "Choose one of the displayed salvage actions.", 0
        careful = choice_id == stage["correct"]
        session["score"] += 2 if careful else 0
        if careful and session.get("dial_moves",0)>0 and session.get("dial",0)==(session["challenges"][session["step"]]*2+1)%5:
            session["precision"]=session.get("precision",0)+1
        session["choices"].append(choice_id)
        base, extra = divmod(max(3, definition.minutes - 2), 3)
        duration = base + int(session['step'] < extra)
        if session["step"] < 2:
            session["step"] += 1
            session["dial"]=(session["challenges"][session["step"]]+4)%5
            session["dial_moves"]=0
            return True, "You preserve the useful parts." if careful else "Some finer parts are damaged, but basic scraps remain recoverable.", duration
        outputs = self.roll_outputs(definition.item_id, session["score"], session["skill_level"],
                                    world_seed, session["attempt"], session["tool_bonus"]+session.get("precision",0)*4)
        for iid, amount in outputs.items():
            inv.add(iid, amount)
        rare_ids = {drop.item_id for drop in definition.rare_yields}
        gain = self._practice(session["score"], definition.difficulty)
        message = "Salvaged " + self.registry.items[definition.item_id].name + ": " + ", ".join(
            f"{self.registry.items[iid].name} x{amount}" for iid, amount in sorted(outputs.items()))
        message += f". Care {session['score']}/6, precision {session.get('precision',0)}/3; salvaging practice +{gain}."
        self.state.player_salvage_log.append({
            "item_id": definition.item_id, "name": self.registry.items[definition.item_id].name,
            "attempt": session["attempt"], "completed_minute": minute + duration,
            "score": session["score"], "max_score": 6, "outputs": dict(outputs),
            "rare_outputs": {iid: amount for iid, amount in outputs.items() if iid in rare_ids},
            "skill_level": self._level(), "skill_xp": self.state.player_salvaging_xp,
            "xp_gained": gain, "message": message,
        })
        del self.state.player_salvage_log[:-SALVAGE_LOG_LIMIT]
        self.state.player_salvage_session = {}
        return True, message, duration
