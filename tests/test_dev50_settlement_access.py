"""Facade doors, crossable gates and cache-safe saved-town access repairs."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.audit_settlement_layouts import ARCHETYPES, POPULATIONS, inspect_skeleton, synthetic_fixture
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.canonical import canonical_hash
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.property_intrusion import PropertySecuritySystem
from worldseed.systems.settlement_access import apply_access_delta, prepare_access_repairs
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState
from worldseed.world.regional_plan import StructurePiecePlan


class SettlementAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.registry=ContentRegistry.load(DATA_DIR)

    def test_v12_all_ranks_and_economies_have_south_facades_and_passable_gate_pairs(self):
        for archetype in ARCHETYPES:
            for population in POPULATIONS:
                with self.subTest(archetype=archetype,population=population):
                    world,region,uid=synthetic_fixture(self.registry,archetype,population,version=12)
                    skeleton=SettlementSkeletonPlanner(world).plan(region,uid,population,persist=False)
                    self.assertFalse(inspect_skeleton(world,self.registry,skeleton,require_all_resources=True))
                    self.assertTrue(any(s.enclosed for s in skeleton.structures))
                    for structure in skeleton.structures:
                        if not structure.enclosed:continue
                        x,y=structure.entrance;cells=set(map(tuple,structure.footprint))
                        self.assertNotIn((x,y+1),cells)
                        self.assertIn((x,y-1),cells)
                    cx,cy=skeleton.plan.anchor_x,skeleton.plan.anchor_y
                    radius={"homestead":18,"hamlet":26,"village":36,"town":46,"city":58}[skeleton.plan.rank]
                    self.assertTrue(all(max(abs(x-cx),abs(y-cy))<=radius+10 for x,y in skeleton.plan.gateway_cells))

    def test_real_strategic_route_gateway_is_not_shortened(self):
        world,region,uid=synthetic_fixture(self.registry,"mining",45,version=12)
        skeleton=SettlementSkeletonPlanner(world).plan(region,uid,45,persist=False,route_links=[{
            "route_id":"route:real","direction":"east","portal_cell":(511,256),"road_class":"road"}])
        road=next(r for r in skeleton.roads if r.route_id=="route:real")
        self.assertGreater(road.polyline[-1][0]-256,60)
        self.assertIn(tuple(road.polyline[-1]),skeleton.plan.gateway_cells)

    def test_outdoor_road_projection_wins_over_quarry_base_without_hiding_solid_fixtures(self):
        road=SimpleNamespace(uid="road:yard",road_class="service_path",polyline=[(0,0),(1,0)])
        solid=next(p for p in self.registry.settlement_pieces.values()
                   if p.category=="furniture" and not p.passable)
        pieces=[StructurePiecePlan("piece:quarry-road","","core:quarry_ground_piece",0,0,role="quarry_ground"),
                StructurePiecePlan("piece:quarry-yard","","core:quarry_ground_piece",0,1,role="quarry_ground"),
                StructurePiecePlan("piece:fixture-road","",solid.id,1,0,role="worksite_fixture")]
        skeleton=SimpleNamespace(parcels=(),roads=(road,),structures=(),rooms=(),pieces=pieces)
        physical=SettlementPhysicalizationSystem(None,self.registry,None,None)
        physical._index_skeleton("settlement:test",skeleton)
        road_cell=physical.cell_at(WorldPos(0,0,0))
        self.assertEqual((road.uid,),road_cell.road_ids)
        self.assertEqual(physical._road_piece("service_path"),road_cell.ground_piece_id)
        self.assertEqual("=",physical.glyph_at(WorldPos(0,0,0)))
        self.assertEqual("core:quarry_ground_piece",physical.cell_at(WorldPos(0,1,0)).ground_piece_id)
        self.assertEqual("q",physical.glyph_at(WorldPos(0,1,0)))
        self.assertEqual(solid.glyph,physical.glyph_at(WorldPos(1,0,0)))
        self.assertFalse(physical.passable(WorldPos(1,0,0)))

    def test_v11_activation_repairs_preserve_base_cache_ids_locks_and_quantities(self):
        with tempfile.TemporaryDirectory(prefix="worldseed-access-") as directory:
            db=WorldDatabase.create(Path(directory)/"access.db","Access repair",b"layout-audit".hex())
            try:
                world,region,uid=synthetic_fixture(self.registry,"agrarian",45,version=11,cache=db)
                planner=SettlementSkeletonPlanner(world)
                base=planner.plan(region,uid,45)
                frozen=base.to_dict()
                entrances={p.structure_plan_id:p.uid for p in base.pieces if p.role=="entrance"}
                repaired=prepare_access_repairs(base,world,self.registry)
                self.assertEqual(frozen,base.to_dict())
                self.assertEqual(canonical_hash(frozen),canonical_hash(db.load_generated_settlement_plan(uid,11)))
                self.assertTrue(db.load_physical_plan_delta(base.plan.uid))
                self.assertFalse(inspect_skeleton(world,self.registry,repaired))
                self.assertEqual(base.plan.housing_capacity,repaired.plan.housing_capacity)
                self.assertEqual(base.plan.workplace_capacity,repaired.plan.workplace_capacity)
                self.assertEqual([r.uid for r in base.rooms],[r.uid for r in repaired.rooms])
                self.assertTrue(db.load_physical_plan_delta(base.plan.uid)["payload"]["footprints"],
                                "fixture must exercise a genuinely flush south facade")
                region_planner=SimpleNamespace(plan=lambda *_args,**_kwargs:region)
                physical=SettlementPhysicalizationSystem(world,self.registry,region_planner,planner)
                physical._skeletons[uid]=base;physical._index_skeleton(uid,base)
                state=LivingWorldState()
                town=SettlementState(uid,"Town",0,0,256,256,45,"culture:test","religion:test","")
                town.stocks={"core:wheat":20};state.settlements[uid]=town
                home=next(s for s in base.structures if s.function=="residence")
                state.npcs["npc:tenant"]=NPCState("npc:tenant","Tenant",34,"farmer",[],256,256,0,uid,"",
                    home_id=home.uid,home_room_id=home.room_ids[0],workplace_id=home.uid)
                civics=SimpleNamespace(ensure_settlement=lambda *_:None,owner_for_structure=lambda *_:uid)
                security=PropertySecuritySystem(state,self.registry,b"layout-audit",physical,civics)
                security.sync_active=lambda:None
                security.sync_settlement(uid)
                sample=next(iter(state.door_security.values()))
                sample.forced=True;sample.picked=True;sample.locked=False;sample.condition=37
                before=state.to_dict()
                physical.sync([town],(0,0))
                security.sync_settlement(uid)
                after=state.to_dict()
                self.assertEqual(before["settlements"],after["settlements"])
                self.assertEqual(before["containers"],after["containers"])
                self.assertEqual(before["npcs"],after["npcs"])
                self.assertTrue(sample.forced);self.assertTrue(sample.picked)
                self.assertFalse(sample.locked);self.assertEqual(37,sample.condition)
                self.assertEqual(entrances,{p.structure_plan_id:p.uid for p in repaired.pieces if p.role=="entrance"})
                for s in repaired.structures:
                    if s.enclosed:
                        x,y=s.entrance
                        self.assertNotIn((x,y+1),set(map(tuple,s.footprint)))
                with patch.object(world,"environment_at",side_effect=AssertionError("stored repair queried terrain")), \
                     patch.object(db,"store_physical_plan_delta",side_effect=AssertionError("stored repair wrote")):
                    self.assertEqual(repaired.to_dict(),prepare_access_repairs(base,world,self.registry).to_dict())
                    self.assertEqual(repaired.to_dict(),planner.read_prepared(uid).to_dict())
                db.connection.execute("DELETE FROM generated_settlement_plans WHERE settlement_uid=?",(uid,));db.commit_generated()
                rebuilt=SettlementSkeletonPlanner(world).plan(region,uid,45)
                self.assertEqual(repaired.to_dict(),rebuilt.to_dict())
                self.assertEqual([],db.verify())
            finally:db.close()

    def test_v10_base_fingerprint_remains_frozen_without_activation(self):
        from tests.test_dev45_farm_compounds import FarmCompoundTests
        fixture=FarmCompoundTests();fixture.registry=self.registry
        self.assertEqual("fa414cc16fd96b867bdd60f3916bbc11c23549c5",fixture.skeleton(version=10,population=45).fingerprint)

    def test_v11_repair_matrix_keeps_actual_doors_and_gates_accessible(self):
        with tempfile.TemporaryDirectory(prefix="worldseed-access-matrix-") as directory:
            db=WorldDatabase.create(Path(directory)/"matrix.db","Access matrix",b"layout-audit".hex())
            try:
                for archetype in ARCHETYPES:
                    for population in POPULATIONS:
                        with self.subTest(archetype=archetype,population=population):
                            world,region,uid=synthetic_fixture(self.registry,archetype,population,version=11,cache=db)
                            base=SettlementSkeletonPlanner(world).plan(region,uid,population)
                            repaired=prepare_access_repairs(base,world,self.registry)
                            self.assertFalse(inspect_skeleton(world,self.registry,repaired,require_all_resources=True))
                            self.assertEqual(base.plan.housing_capacity,repaired.plan.housing_capacity)
                            self.assertEqual(base.plan.workplace_capacity,repaired.plan.workplace_capacity)
                            for structure in repaired.structures:
                                if not structure.enclosed:continue
                                x,y=structure.entrance
                                if (x,y+1) in set(map(tuple,structure.footprint)):
                                    # A frozen 5x4 building may touch its entire
                                    # south neighbor. Retain its safe side door
                                    # rather than shrinking below the 4x4 bound.
                                    rows=[y for _,y in structure.footprint]
                                    self.assertEqual(4,max(rows)-min(rows)+1)
                                    self.assertEqual(archetype,"fishing")
                                    self.assertIn(population,(45,110))
            finally:db.close()

    def test_legacy_pen_repair_rejects_an_inward_step_occupied_by_a_trough(self):
        with tempfile.TemporaryDirectory(prefix="worldseed-gate-") as directory:
            db=WorldDatabase.create(Path(directory)/"gate.db","Gate repair",b"layout-audit".hex())
            try:
                world,region,uid=synthetic_fixture(self.registry,"agrarian",45,version=11,cache=db)
                base=SettlementSkeletonPlanner(world).plan(region,uid,45)
                pen=next(s for s in base.structures if s.function=="animal_pen")
                default=prepare_access_repairs(base,world,self.registry)
                default_gate=tuple(next(s for s in default.structures if s.uid==pen.uid).entrance)
                original_cells=set(map(tuple,pen.footprint))
                original_boundary={p for p in original_cells if any((p[0]+dx,p[1]+dy) not in original_cells
                    for dx,dy in ((0,1),(1,0),(0,-1),(-1,0)))}
                occupied=next((default_gate[0]+dx,default_gate[1]+dy) for dx,dy in ((0,1),(1,0),(0,-1),(-1,0))
                    if (default_gate[0]+dx,default_gate[1]+dy) in original_cells-original_boundary
                    and (default_gate[0]-dx,default_gate[1]-dy) not in original_cells)
                db.connection.execute("DELETE FROM physical_plan_deltas WHERE object_uid=?",(base.plan.uid,));db.commit_generated()
                blocker=StructurePiecePlan("piece:test-blocked-inward",pen.uid,"core:dev43_livestock_trough_piece",*occupied,role="worksite_fixture")
                base.pieces.append(blocker);pen.piece_ids.append(blocker.uid)
                snapshot=base.to_dict();snapshot.pop("fingerprint",None);base.fingerprint=canonical_hash(snapshot)
                repaired=prepare_access_repairs(base,world,self.registry)
                physical=SettlementPhysicalizationSystem(world,self.registry,None,None)
                physical._index_skeleton(uid,repaired)
                changed=next(s for s in repaired.structures if s.uid==pen.uid)
                gate=tuple(changed.entrance);cells=set(map(tuple,changed.footprint))
                self.assertNotEqual(default_gate,gate)
                boundary={p for p in cells if any((p[0]+dx,p[1]+dy) not in cells for dx,dy in ((0,1),(1,0),(0,-1),(-1,0)))}
                self.assertTrue(any((gate[0]+dx,gate[1]+dy) in cells-boundary
                    and physical.passable(WorldPos(gate[0]+dx,gate[1]+dy,0),True)
                    and (gate[0]-dx,gate[1]-dy) not in cells for dx,dy in ((0,1),(1,0),(0,-1),(-1,0))))
                self.assertFalse(inspect_skeleton(world,self.registry,repaired))
            finally:db.close()


if __name__=="__main__":unittest.main()
