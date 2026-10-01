"""Bounded testimony from a resident's home, occupation, skills and known facts.

Rendering these answers never samples the world or discovers anything. The
conversation owner records disclosures only after the player asks a question.
"""
from __future__ import annotations


class NPCKnowledgeSystem:
    def __init__(self, state, registry):
        self.state = state
        self.registry = registry

    def answer(self, npc, topic: str) -> tuple[str, dict[str, list[str]]]:
        rel = npc.relationships.get("player", {})
        trust = int(rel.get("trust", 0))
        threshold = 8 if "suspicious" in npc.traits else 0
        if trust < threshold or self.state.player_crime_heat.get(npc.settlement_id, 0) >= 35:
            return "I am not comfortable sharing that with you yet. Let us get to know one another first.", {}
        town = self.state.settlements.get(npc.settlement_id)
        known = set(npc.knowledge)
        disclosed: dict[str, list[str]] = {}

        def names(catalog, ids):
            return ", ".join(catalog[i].name for i in sorted(set(ids)) if i in catalog)

        if topic == "animals":
            # Residents know their own livestock. Wild species require a known
            # fact rather than querying hidden populations from a chat screen.
            ids = set(getattr(town, "livestock_species_ids", ()) or ())
            ids.update(k[8:] for k in known if k.startswith("species:"))
            ids = sorted(i for i in ids if i in self.registry.species)
            if ids:
                disclosed["discovered_species"] = ids
                return "Animals I can identify here: " + names(self.registry.species, ids) + ". Ask a hunter about wild signs; I cannot promise sightings I have not made.", disclosed
            return "I know our local work and households, but I have no reliable animal sightings to pass on. Ask a hunter or herder for specific signs.", {}
        if topic == "plants":
            ids = set(getattr(town, "crop_ids", ()) or ())
            ids.update(k[5:] for k in known if k.startswith("crop:"))
            label = names(self.registry.crops, ids)
            if label:
                detail = " A farmer can explain soil, seasons, and cultivation." if npc.occupation != "farmer" else " Planting takes real seed, suitable soil, and attention through the growing season."
                return "Crops grown around home: " + label + "." + detail, {}
            return "I have not learned specific plants well enough to identify them safely. A farmer, healer, or gatherer may know more.", {}
        if topic == "resources":
            resources = list(getattr(town, "resource_specializations", ()) or ())
            if resources:
                return "Our local livelihoods are " + " and ".join(str(r).replace("_", " ") for r in resources) + ". We depend on trade for goods those workplaces do not supply.", {}
            return "I can explain my work as a " + npc.occupation.replace("_", " ") + ", but I do not know a confirmed resource deposit to direct you to.", {}
        if topic == "towns":
            ids = {k for k in known if k in self.state.settlements}
            if town: ids.add(town.uid)
            if npc.occupation == "merchant":
                for route in self.state.trade_routes.values():
                    if npc.settlement_id in (route.origin, route.destination):
                        ids.update((route.origin, route.destination))
            ids = sorted(i for i in ids if i in self.state.settlements)
            if ids:
                disclosed["discovered_settlements"] = ids
                return "Towns I can speak about from home or my travels: " + ", ".join(self.state.settlements[i].name for i in ids) + ". A merchant may know more road connections.", disclosed
            return "I do not know another town well enough to give you reliable directions.", {}
        if topic == "skills":
            skills = sorted(((int(v), str(k)) for k, v in npc.skills.items() if int(v) > 0), reverse=True)
            if skills:
                level, skill = skills[0]
                return f"My strongest practiced skill is {skill.replace('_', ' ')} ({level}). " + {
                    "farming": "Learn the soil before choosing seed; keep a clear path into every growing row.",
                    "woodcutting": "Leave yourself a clear working position and carry the timber to storage.",
                    "mining": "Follow accessible veins, keep a return route, and bring the proper tools.",
                    "hauling": "Goods stay in your pack until delivered; plan the return trip before loading it.",
                }.get(skill, "Start with suitable tools and real materials. Practice carefully; advice alone will not replace experience."), {}
            return "I can pass on what daily life as a " + npc.occupation.replace("_", " ") + " has taught me, but I cannot claim formal skill training. Respect working spaces and ask the people doing the job.", {}
        return "Ask me about animals, plants, resources, towns, or skills.", {}

    def disclose(self, facts: dict[str, list[str]]) -> None:
        for field in ("discovered_species", "discovered_settlements"):
            if field in facts:
                setattr(self.state, field, sorted(set(getattr(self.state, field)) | set(facts[field])))
