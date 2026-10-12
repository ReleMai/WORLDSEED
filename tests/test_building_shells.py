import unittest
from types import SimpleNamespace

from worldseed.core.coords import WorldPos
from worldseed.systems.building_shells import shell_from_plan
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.property_intrusion import PropertyStorageSystem
from worldseed.systems.state import LivingWorldState, SettlementState, ContainerState, pos_key
from worldseed.world.regional_plan import StructurePlanState, StructurePiecePlan, RoomPlanState, RoadSegmentPlan


class BuildingShellTests(unittest.TestCase):
    def fixture(self,function="residence"):
        structure=StructurePlanState("building:test","plan:test","core:house",function,
            footprint=[(x,y) for y in range(3,6) for x in range(3,6)],entrance=(4,5),enclosed=True)
        pieces=[StructurePiecePlan("door:test",structure.uid,"core:door",4,5,role="entrance"),
                StructurePiecePlan("fixture:test",structure.uid,"core:chest",4,4,role="fixture")]
        pieces.extend(StructurePiecePlan(f"floor:{x}:{y}",structure.uid,"core:floor",x,y,layer="ground",role="floor") for x,y in structure.footprint)
        room=RoomPlanState("room:test",structure.uid,"bedroom",list(structure.footprint),fixture_ids=["fixture:test"],area=9)
        roads=[RoadSegmentPlan("road:test",road_class="path",polyline=[(4,8),(4,7),(4,6),(4,5)])]
        registry=SimpleNamespace(settlement_pieces={
            "core:door":SimpleNamespace(id="core:door",category="door",layer="structure",passable=True,blocks_sight=False,glyph="+",name="Door"),
            "core:chest":SimpleNamespace(id="core:chest",category="fixture",layer="fixture",passable=False,blocks_sight=False,glyph="C",name="Chest"),
            "core:floor":SimpleNamespace(id="core:floor",category="floor",layer="ground",passable=True,blocks_sight=False,glyph=".",name="Floor"),
            "core:footpath_piece":SimpleNamespace(id="core:footpath_piece",category="road",layer="ground",passable=True,blocks_sight=False,glyph=".",name="Path"),
        })
        physical=SettlementPhysicalizationSystem(None,registry,None,None)
        skeleton=SimpleNamespace(structures=[structure],pieces=pieces,rooms=[room],roads=roads,parcels=[])
        physical._skeletons["settlement:test"]=skeleton
        physical._index_skeleton("settlement:test",skeleton)
        return physical,structure,skeleton,registry

    def test_intact_enclosed_footprint_is_solid_including_unlocked_door(self):
        physical,structure,_,_=self.fixture()
        for x,y in structure.footprint:
            self.assertTrue(physical.shell_blocks(WorldPos(x,y)))
            self.assertFalse(physical.passable(WorldPos(x,y)))
            self.assertTrue(physical.blocks_sight(WorldPos(x,y)))
        door=physical.door_at(WorldPos(4,5))
        self.assertEqual(door.structure_piece_uid,"door:test")
        self.assertTrue(physical.passable(WorldPos(4,6)))
        self.assertIsNone(physical.shell_at(WorldPos(4,5,-1)))

    def test_shell_preserves_source_identity_and_exterior_road_frontage(self):
        physical,structure,skeleton,_=self.fixture()
        shell=physical.shell_at(WorldPos(4,4))
        self.assertEqual(shell.uid,structure.uid)
        self.assertEqual(shell.door_uid,"door:test")
        self.assertEqual(shell.bounds,(3,3,5,5))
        self.assertEqual(shell.door_side,"south")
        self.assertEqual(physical.frontage_for(structure.uid),WorldPos(4,6))
        self.assertEqual(physical.destination_for(structure.uid),WorldPos(4,6))
        self.assertEqual(physical.shells_in_bounds(4,4,4,4),(shell,))
        projected=physical.cell_at(WorldPos(4,4))
        self.assertFalse(projected.fixture_piece_id)
        self.assertFalse(projected.ground_piece_id)
        self.assertFalse(projected.room_id)
        self.assertEqual(skeleton.rooms[0].fixture_ids,["fixture:test"])
        self.assertEqual(physical._cells[(4,4)].fixture_piece_uid,"fixture:test")

    def test_open_yards_and_destroyed_buildings_are_not_shells(self):
        _,structure,skeleton,_=self.fixture()
        structure.enclosed=False
        self.assertIsNone(shell_from_plan(structure,"settlement:test",skeleton.pieces))
        structure.enclosed=True;structure.destroyed=True
        self.assertIsNone(shell_from_plan(structure,"settlement:test",skeleton.pieces))
        structure.destroyed=False;structure.condition=0
        self.assertIsNone(shell_from_plan(structure,"settlement:test",skeleton.pieces))

    def test_load_displacement_is_bounded_and_uses_supplied_prepared_safety(self):
        physical,_,_,_=self.fixture()
        source=WorldPos(4,4)
        self.assertEqual(physical.displace_shell_position(source,lambda pos:pos==WorldPos(4,6)),WorldPos(4,6))
        self.assertIsNone(physical.displace_shell_position(source,lambda pos:False,max_radius=2))
        outside=WorldPos(30,30)
        self.assertEqual(physical.displace_shell_position(outside,lambda pos:False),outside)

    def test_workshop_storage_moves_inside_without_copying_goods(self):
        physical,structure,_,registry=self.fixture("workshop")
        # This isolated shell fixture has no item catalog; it tests relocation,
        # not the separate once-per-village salvage origin system.
        registry.items={}
        state=LivingWorldState()
        town=SettlementState("settlement:test","Millford",0,0,4,4,20,"culture:test","religion:test","")
        town.stocks={"core:wood":10};state.settlements[town.uid]=town
        storage=ContainerState("property-storage:"+structure.uid,4,4,0,"npc:worker",100000,100000,
            {"core:wood":3},kind="property",property_id=structure.uid,settlement_id=town.uid)
        state.containers[pos_key(4,4,0)]=storage
        civics=SimpleNamespace(owner_for_structure=lambda *_:"npc:worker",ensure_settlement=lambda *_:None)
        system=PropertyStorageSystem(state,registry,b"shell-test",physical,civics)
        system.sync_settlement(town.uid)
        frontage=physical.frontage_for(structure.uid)
        self.assertEqual(storage.interior_space_id,'interior:'+structure.uid)
        self.assertIs(state.containers['indoor-storage:'+storage.uid],storage)
        self.assertNotIn(pos_key(frontage.x,frontage.y,frontage.z),state.containers)
        self.assertEqual(storage.items,{"core:wood":3})
        self.assertEqual(town.stocks,{"core:wood":10})
        # The current physical profile has a tool chest and an independent
        # tabletop slot. Neither may duplicate the migrated worker storage.
        self.assertEqual(len(state.containers),3)
        indoor=next(c for c in state.containers.values() if c.profile_id=='core:tool_chest')
        tabletop=next(c for c in state.containers.values() if c.profile_id=='core:tabletop')
        self.assertEqual(indoor.profile_id,"core:tool_chest")
        self.assertEqual(indoor.items,{})
        self.assertEqual(tabletop.items,{})
        self.assertEqual(len({c.uid for c in state.containers.values()}),3)
        self.assertNotIn(pos_key(4,4,0),state.containers)
        position=(storage.x,storage.y,storage.z)
        system.sync_settlement(town.uid)
        self.assertEqual((storage.x,storage.y,storage.z),position)


if __name__=="__main__":unittest.main()
