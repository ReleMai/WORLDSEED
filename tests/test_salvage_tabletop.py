"""WORLDSEED tabletop salvaging and profession progression contracts."""
import unittest
from copy import deepcopy
from types import SimpleNamespace

from worldseed.content.registry import ContentRegistry, ItemDef, SalvageDef, SalvageRareYield
from worldseed.entities.components import Inventory
from worldseed.persistence.validation import validate_sim_state
from worldseed.systems.salvaging import SalvagingSystem
from worldseed.systems.salvage_perks import PERKS, PATHS, LEVEL_GATES
from worldseed.systems.state import LivingWorldState

SEED = b"interactive-salvage-v2"

def fixture(method="unfasten", copies=2):
    registry = ContentRegistry()
    registry.items = {
        "test:object": ItemDef("test:object", "Damaged object"),
        "test:parts": ItemDef("test:parts", "Reusable pieces"),
        "test:rare": ItemDef("test:rare", "Hidden fixture"),
    }
    registry.salvage["test:object"] = SalvageDef(
        "test:salvage_object", "test:object", 12, 4,
        {"test:parts": (1, 4)}, (SalvageRareYield("test:rare", 1, 1, 1),),
        method=method, description="Inspect faults, joints and layered materials.")
    state = LivingWorldState(player_crafting_discovery_enabled=True)
    inv = Inventory({"test:object": copies})
    return SalvagingSystem(state, registry), state, inv, registry

def complete(system, inv, careful=True, reload_each=False):
    system.act("inspect",inv,SEED,minute=50)
    while system.session_view():
        project = system.state.player_salvage_session
        select = next(i for i,n in enumerate(project["nodes"]) if not n["done"] and (
            n["depends"] < 0 or project["nodes"][n["depends"]]["done"]))
        system.act("select:"+str(select),inv,SEED,minute=55)
        session = system.session_view()
        assert session["selected_node"] == select
        if careful:
            system.act("survey",inv,SEED,minute=56)
        ideal = project["nodes"][select]["ideal"]
        game_ops = {"disassembly":("unfasten","wedge","cut"),
                    "fracture":("tap","wedge","strike"),
                    "recovery":("unpick","wash","dry","cut")}[project["game"]]
        operation = ideal if careful else next(op for op in game_ops if op != ideal)
        ok, message, elapsed = system.act("work:"+operation,inv,SEED,minute=60+select)
        assert ok, message
        if reload_each and system.session_view():
            saved = system.state.to_dict()
            assert not validate_sim_state(saved), validate_sim_state(saved)
            reconstructed = LivingWorldState.from_dict(saved)
            saved["player_salvage_session"]["nodes"].clear()
            assert reconstructed.player_salvage_session["nodes"]
            system = SalvagingSystem(reconstructed,system.registry)
    return system

class TabletopSalvageTests(unittest.TestCase):
    def test_all_three_material_games_have_distinct_interactive_mechanics(self):
        expected = {"unfasten":"disassembly", "crush":"fracture", "strip":"recovery"}
        for method, game in expected.items():
            with self.subTest(game=game):
                system, state, inv, _ = fixture(method, 1)
                self.assertTrue(system.begin_game("test:object",inv,SEED,40)[0])
                self.assertEqual(system.session_view()["game"],game)
                self.assertEqual(inv.count("test:object"),0)
                self.assertEqual(system.session_view()["stage_count"],4)
                self.assertFalse(system.act("work:cut",inv,SEED)[0])
                self.assertEqual(validate_sim_state(state.to_dict()),[])
                system = complete(system,inv,reload_each=True)
                self.assertEqual(system.state.player_salvage_log[-1]["score"],100)
                self.assertEqual(system.state.player_salvage_log[-1]["max_score"],100)
                self.assertGreaterEqual(inv.count("test:parts"),1)
                self.assertEqual(validate_sim_state(system.state.to_dict()),[])

    def test_invalid_actions_do_not_advance_or_duplicate_output(self):
        system,state,inv,_=fixture("crush",1)
        system.begin_game("test:object",inv,SEED,40)
        system.act("inspect",inv,SEED)
        before=deepcopy(state.to_dict())
        self.assertFalse(system.act("work:unfasten",inv,SEED)[0])
        self.assertFalse(system.act("select:999",inv,SEED)[0])
        self.assertEqual(before,state.to_dict())
        finished=complete_without_inspection(system,inv)
        after=deepcopy(state.to_dict()),dict(inv.items)
        self.assertFalse(system.act("work:tap",inv,SEED)[0])
        self.assertEqual(after,(state.to_dict(),dict(inv.items)))
        self.assertEqual(len(state.player_salvage_log),1)
        self.assertLess(finished,100)

    def test_quality_and_output_survive_reload_deterministically(self):
        signatures=[]
        for reload_each in (False,True):
            system, state, inv, _ = fixture("strip",1)
            self.assertTrue(system.begin_game("test:object",inv,SEED,40)[0])
            system=complete(system,inv,reload_each=reload_each)
            signatures.append((system.state.player_salvage_log,dict(inv.items)))
        self.assertEqual(signatures[0],signatures[1])

    def test_perk_points_path_prerequisites_respec_and_legacy(self):
        system,state,inv,_=fixture()
        self.assertEqual(system.perk_view()["points"],0)
        self.assertFalse(system.buy_perk("conservator")[0])
        state.player_skills["salvaging"]=10
        self.assertFalse(system.buy_perk("lost_arts")[0])
        for path in PATHS[:2]:
            for perk in sorted((p for p in PERKS.values() if p.path==path),key=lambda p:p.tier):
                self.assertTrue(system.buy_perk(perk.id)[0])
        self.assertEqual(system.perk_view()["points"],0)
        self.assertFalse(system.buy_perk("tell_tale_marks")[0])
        self.assertEqual(validate_sim_state(state.to_dict()),[])
        self.assertTrue(system.reset_perks()[0])
        self.assertEqual(system.perk_view()["points"],10)
        self.assertFalse(system.reset_perks()[0])
        self.assertEqual(LivingWorldState.from_dict({"player_skills":{"salvaging":3}}).player_salvage_perks,[])

    def test_precision_caps_and_wreckbreaker_batch(self):
        system,state,inv,_=fixture("unfasten",1)
        state.player_skills["salvaging"]=10
        for perk in ("seam_sense","steady_hands","intact_recovery","gentle_undo","conservator"):
            self.assertTrue(system.buy_perk(perk)[0])
        self.assertTrue(system.begin_game("test:object",inv,SEED)[0])
        system=complete(system,inv)
        self.assertIn("test:rare",system.state.player_salvage_log[-1]["outputs"])
        batch,state,items,_=fixture("crush",7)
        state.player_skills["salvaging"]=10
        for perk in ("fast_hands","sorted_scrap","sweep_job","makeshift_rig","wreckbreaker"):
            self.assertTrue(batch.buy_perk(perk)[0])
        self.assertFalse(batch.quick_batch("test:object",7,items,SEED)[0])
        self.assertTrue(batch.quick_batch("test:object",6,items,SEED)[0])
        self.assertEqual(state.salvaging_attempts,6)
        self.assertEqual(len(state.player_salvage_log),6)
        self.assertEqual(items.count("test:object"),1)
        self.assertEqual(validate_sim_state(state.to_dict()),[])

    def test_lost_arts_requires_three_distinct_sources_and_a_real_workshop(self):
        system,state,inv,registry=fixture("unfasten",3)
        state.player_skills["salvaging"]=10
        for perk in ("tell_tale_marks","workshop_whisper","notes_from_ruins","targeted_search","lost_arts"):
            self.assertTrue(system.buy_perk(perk)[0])
        registry.recipes={"test:recipe":SimpleNamespace(
            station="test:workshop",inputs={"test:parts":1},id="test:recipe",name="Recovered fitting",knowledge="")}
        for number in range(3):
            item_id="test:object" if number==0 else "test:object"+str(number)
            if number:
                registry.items[item_id]=ItemDef(item_id,"Damaged object "+str(number))
                registry.salvage[item_id]=SalvageDef("test:salvage_"+str(number),item_id,12,4,
                    {"test:parts":(1,4)},method="unfasten",description="Old fittings.")
                inv.add(item_id,1)
            self.assertTrue(system.begin_game(item_id,inv,SEED)[0])
            system=complete(system,inv)
        self.assertEqual(len(state.player_salvage_dossiers["test:workshop"]),3)
        self.assertFalse(system.claim_dossier("test:workshop",set())[0])
        self.assertTrue(system.claim_dossier("test:workshop",{"test:workshop"})[0])
        self.assertIn("test:recipe",state.player_discovered_recipes)
        self.assertEqual(state.player_salvage_dossiers["test:workshop"],[])

    def test_fracture_impacts_damage_adjacent_sections_and_can_be_corrected(self):
        system,state,inv,_=fixture("crush",1)
        state.player_skills["salvaging"]=10
        for perk in ("seam_sense","steady_hands","intact_recovery","gentle_undo"):
            self.assertTrue(system.buy_perk(perk)[0])
        system.begin_game("test:object",inv,SEED)
        system.act("inspect",inv,SEED)
        adjacent=state.player_salvage_session["nodes"][1]
        ideal=state.player_salvage_session["nodes"][0]["ideal"]
        wrong="strike" if ideal!="strike" else "tap"
        self.assertTrue(system.act("work:"+wrong,inv,SEED)[0])
        self.assertGreater(adjacent["damage"],0)
        self.assertTrue(system.session_view()["can_undo"])
        self.assertTrue(system.act("undo",inv,SEED)[0])
        self.assertEqual(adjacent["damage"],0)
        self.assertEqual(state.player_salvage_session["step"],0)
        self.assertEqual(validate_sim_state(state.to_dict()),[])

    def test_makeshift_quick_action_never_bypasses_equipment_protection(self):
        from dataclasses import replace
        system,state,inv,registry=fixture("strip",2)
        state.player_skills["salvaging"]=10
        for perk in ("fast_hands","sorted_scrap","sweep_job","makeshift_rig"):
            self.assertTrue(system.buy_perk(perk)[0])
        d=registry.salvage["test:object"]
        registry.salvage["test:object"]=replace(d,tool_qualities={"cut":1})
        self.assertFalse(system.can_start("test:object",inv)[0])
        self.assertTrue(system.can_quick("test:object",inv)[0])
        self.assertTrue(system.quick_batch("test:object",1,inv,SEED)[0])
        self.assertEqual(inv.count("test:object"),1)
        state.player_equipment["hands"]="test:object"
        self.assertFalse(system.can_quick("test:object",inv)[0])

def complete_without_inspection(system,inv):
    while system.session_view():
        project=system.state.player_salvage_session
        index=next(i for i,n in enumerate(project["nodes"]) if not n["done"] and (
            n["depends"] < 0 or project["nodes"][n["depends"]]["done"]))
        system.act("select:"+str(index),inv,SEED)
        ideal=project["nodes"][index]["ideal"]
        option=next(op for op in ("tap","wedge","strike") if op!=ideal)
        ok,msg,_=system.act("work:"+option,inv,SEED)
        assert ok,msg
    return system.state.player_salvage_log[-1]["score"]

if __name__ == "__main__":
    unittest.main()
