import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.systems.activities import ActivitySystem
from worldseed.systems.mining_profession import MiningProfessionSystem
from worldseed.systems.physical_goods import SettlementPhysicalGoodsSystem
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState


class FakeEntrance:
    def __init__(self, x=5, y=5, depth=4):
        self.x=x;self.y=y;self.depth=depth;self.relief=1000;self.elevation=42000


class FakeCaves:
    def __init__(self):
        self.entry=FakeEntrance()

    def entrances_near(self, x, y, radius):
        distance=abs(self.entry.x-int(x))+abs(self.entry.y-int(y))
        return (self.entry,) if distance<=int(radius) else ()

    def has_connector(self, pos):
        return (pos.x,pos.y)==(self.entry.x,self.entry.y) and 0>=pos.z>=-self.entry.depth

    def terrain_at(self, pos):
        if (pos.x,pos.y,pos.z)==(7,5,-3):
            return "core:iron_vein"
        if self.has_connector(pos):
            return "core:shaft"
        # Landing neighborhood and most open cells are floor. A sparse wall ring
        # gives the miner a stone fallback while preserving the iron target.
        if abs(pos.x-self.entry.x)+abs(pos.y-self.entry.y)<=3:
            return "core:cave_floor"
        return "core:cave_wall"


class FakeWorld:
    def __init__(self, registry):
        self.registry=registry
        self.generator=SimpleNamespace(caves=FakeCaves())
        self.deltas={}

    def tile_at(self, pos):
        tid=self.deltas.get((pos.x,pos.y,pos.z))
        if tid is None:
            if pos.z<0:
                tid=self.generator.caves.terrain_at(pos)
            elif (pos.x,pos.y)==(5,5):
                tid="core:cave_mouth"
            else:
                tid="core:grass"
        return SimpleNamespace(terrain=self.registry.terrains[tid],terrain_id=tid)

    def is_passable(self, pos):
        return bool(self.tile_at(pos).terrain.passable)

    def set_terrain(self, pos, terrain_id):
        self.deltas[(pos.x,pos.y,pos.z)]=str(terrain_id)


class FakePhysicalization:
    def __init__(self, world):
        self.world=world
        self.room=SimpleNamespace(
            uid="room:mining-house",
            cells=[(0,0),(1,0),(0,1),(1,1)],
            structure_plan_id="structure:mining-house",
        )
        self.skeleton=SimpleNamespace(pieces=[],rooms=[self.room],structures=[])

    def skeleton_for(self, settlement_id):
        return self.skeleton

    def room_by_id(self, room_id):
        return self.room if room_id==self.room.uid else None

    def destination_for(self, structure_id, room_id=""):
        return WorldPos(0,0,0)

    def passable(self, pos, world_passable=True):
        return bool(world_passable)

    def cell_at(self, pos):
        return SimpleNamespace(structure_id="structure:mining-house") if pos.z==0 else None


class Phase4MinerProfessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def fixture(self):
        state=LivingWorldState()
        town=SettlementState(
            uid="settlement:mine",
            name="Mine Town",
            region_x=0,region_y=0,x=0,y=0,population=45,
            culture_id="culture:test",religion_id="religion:test",faction_id="faction:test",
        )
        state.settlements[town.uid]=town
        npc=NPCState(
            uid="npc:miner",name="Miner",age=36,occupation="miner",traits=["patient"],
            x=1,y=1,z=0,settlement_id=town.uid,faction_id=town.faction_id,
            home_id="home:miner",workplace_id="structure:mining-house",work_room_id="room:mining-house",
        )
        state.npcs[npc.uid]=npc
        world=FakeWorld(self.registry)
        physical=FakePhysicalization(world)
        activities=ActivitySystem(state,self.registry,physical,world)
        goods=SettlementPhysicalGoodsSystem(state,self.registry)
        mining=MiningProfessionSystem(state,self.registry,b"phase4-miner-test",world,physical,activities,goods)
        return state,town,npc,world,physical,activities,goods,mining

    def test_miner_has_persistent_profession_skills_and_inventory(self):
        state,town,npc,world,physical,activities,goods,mining=self.fixture()
        mining.ensure_profile(npc)
        self.assertEqual(set(("mining","prospecting","hauling","cavecraft"))-set(npc.skills),set())
        self.assertTrue(all(1<=npc.skills[name]<=10 for name in ("mining","prospecting","hauling","cavecraft")))
        npc.inventory["core:iron_ore"]=2
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.npcs[npc.uid].inventory["core:iron_ore"],2)
        self.assertEqual(restored.npcs[npc.uid].skills,npc.skills)

    def test_ore_value_uses_rarity_distance_and_depth(self):
        state,town,npc,world,physical,activities,goods,mining=self.fixture()
        near_stone=mining.ore_unit_value("core:stone","core:cave_wall",12,1)
        far_stone=mining.ore_unit_value("core:stone","core:cave_wall",120,1)
        far_iron=mining.ore_unit_value("core:iron_ore","core:iron_vein",120,5)
        self.assertGreater(far_stone,near_stone)
        self.assertGreater(far_iron,far_stone)

    def test_miner_plans_real_cave_trip_and_reserves_material_face(self):
        state,town,npc,world,physical,activities,goods,mining=self.fixture()
        tasks=mining.plan_work(npc,town,600)
        self.assertTrue(tasks)
        self.assertEqual(tasks[0]["kind"],"move")
        self.assertEqual((tasks[0]["x"],tasks[0]["y"],tasks[0]["z"]),(5,5,0))
        self.assertEqual(tasks[1]["kind"],"mining_transition")
        self.assertEqual(tasks[1]["target_z"],-3)
        self.assertTrue(any(t.get("action")=="mine_extract" for t in tasks))
        self.assertEqual(tasks[-1]["action"],"mining_deposit")
        trip=next(iter(state.mining_trips.values()))
        self.assertEqual(trip.ore_item_id,"core:iron_ore")
        self.assertEqual(trip.ore_terrain_id,"core:iron_vein")
        self.assertGreater(trip.unit_value,0)
        reservation=next(iter(state.activity_reservations.values()))
        self.assertEqual(reservation.target_uid,"mineral-face:7:5:-3")

    def test_extract_carries_real_ore_then_deposits_into_mining_house(self):
        state,town,npc,world,physical,activities,goods,mining=self.fixture()
        tasks=mining.plan_work(npc,town,600)
        trip=next(iter(state.mining_trips.values()))
        npc.x,npc.y,npc.z=trip.stand_x,trip.stand_y,trip.target_z
        self.assertTrue(mining.complete_extract(npc,trip.uid,640))
        self.assertGreater(npc.inventory.get("core:iron_ore",0),0)
        self.assertEqual(world.tile_at(WorldPos(trip.target_x,trip.target_y,trip.target_z)).terrain_id,"core:cave_floor")

        storage=next(c for c in state.containers.values() if c.uid==trip.storage_uid)
        town.stocks["core:iron_ore"]=0
        npc.x,npc.y,npc.z=storage.x,storage.y,storage.z
        self.assertTrue(mining.deposit(npc,town,trip.uid,storage.uid,700))
        self.assertEqual(npc.inventory.get("core:iron_ore",0),0)
        self.assertEqual(storage.items.get("core:iron_ore",0),trip.delivered_quantity)
        self.assertGreater(trip.delivered_value,0)
        self.assertEqual(town.stocks["core:iron_ore"],0, "physical deposit must not duplicate aggregate stock")
        transfer=next(iter(state.physical_goods_transfers.values()))
        self.assertEqual(transfer.source_kind,"mining_trip")
        self.assertEqual(transfer.container_uid,storage.uid)
        self.assertGreater(transfer.total_value,0)

    def test_physical_goods_support_future_settlement_input_withdrawal(self):
        state,town,npc,world,physical,activities,goods,mining=self.fixture()
        mining.ensure_profile(npc)
        storage=mining.ensure_mining_house_storage(npc,town)
        storage.items["core:coal"]=5
        row=goods.withdraw(
            npc,storage,720,items={"core:coal":2},
            source_kind="workplace_input",source_uid="smith:test",
        )
        self.assertIsNotNone(row)
        self.assertEqual(npc.inventory["core:coal"],2)
        self.assertEqual(storage.items["core:coal"],3)
        self.assertEqual(row.direction,"withdraw")


if __name__=="__main__":
    unittest.main()
