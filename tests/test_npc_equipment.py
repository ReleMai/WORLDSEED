import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.persistence.validation import validate_sim_state
from worldseed.systems.npc_equipment import NPCEquipmentSystem, starting_equipment_stock
from worldseed.systems.physical_goods import SettlementPhysicalGoodsSystem
from worldseed.systems.state import ContainerState, LivingWorldState, NPCState, SettlementState


class NPCEquipmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def make(self, occupation="miner"):
        state = LivingWorldState()
        town = SettlementState("town:test", "Test", 0, 0, 10, 10, 40, "", "", "")
        npc = NPCState("npc:test", "Test Worker", 30, occupation, [], 10, 10, 0, town.uid, "", wealth=37)
        state.settlements[town.uid] = town
        state.npcs[npc.uid] = npc
        return state, town, npc, NPCEquipmentSystem(state, self.registry)

    @staticmethod
    def goods_total(town, npc, containers=()):
        total = Counter(town.stocks)
        total.update(npc.inventory)
        for container in containers:
            total.update(container.items)
        return +total

    def test_issuance_conserves_supply_and_cash_and_is_idempotent(self):
        state, town, npc, equipment = self.make()
        town.stocks.update({"core:iron_pick": 1, "core:leather_vest": 1, "core:leather_leggings": 1})
        before = self.goods_total(town, npc)
        cash = npc.wealth + town.wealth
        self.assertEqual(equipment.provision_settlement(town), 3)
        self.assertEqual(equipment.provision_settlement(town), 0)
        self.assertEqual(npc.equipment["hand"], "core:iron_pick")
        self.assertEqual(self.goods_total(town, npc), before)
        self.assertEqual(npc.wealth + town.wealth, cash)
        self.assertEqual(npc.wealth, 37)
        self.assertEqual(len(state.physical_goods_transfers), 1)

    def test_shortage_can_retry_and_carried_tool_is_not_duplicated(self):
        state, town, npc, equipment = self.make()
        self.assertEqual(equipment.provision_settlement(town), 0)
        self.assertEqual(npc.inventory, {})
        town.stocks["core:stone_pick"] = 1
        self.assertEqual(equipment.provision_settlement(town), 1)
        self.assertEqual(npc.inventory["core:stone_pick"], 1)
        npc.equipment.clear()
        equipment.provision_settlement(town)
        self.assertEqual(npc.inventory["core:stone_pick"], 1)
        self.assertEqual(len(state.physical_goods_transfers), 1)

    def test_equipment_reserves_inventory_unit_during_cargo_deposit(self):
        state, town, npc, equipment = self.make()
        npc.inventory = {"core:iron_pick": 2, "core:iron_ore": 3}
        equipment.provision_settlement(town)
        container = ContainerState("store:test", 10, 10, 0, town.uid, 100000, 100000, settlement_id=town.uid)
        goods = SettlementPhysicalGoodsSystem(state, self.registry)
        goods.deposit(npc, container, 20)
        self.assertEqual(npc.inventory, {"core:iron_pick": 1})
        self.assertEqual(container.items, {"core:iron_pick": 1, "core:iron_ore": 3})
        self.assertEqual(npc.equipment, {"hand": "core:iron_pick"})

    def test_owned_property_supply_is_transferred_without_debiting_town_again(self):
        state, town, npc, equipment = self.make()
        npc.home_id = "house:test"
        container = ContainerState(
            "store:test", 10, 10, 0, npc.uid, 100000, 100000,
            items={"core:iron_pick": 1}, kind="property", settlement_id=town.uid, property_id=npc.home_id,
        )
        state.containers["10,10,0"] = container
        before = self.goods_total(town, npc, (container,))
        equipment.provision_settlement(town)
        self.assertEqual(npc.inventory, {"core:iron_pick": 1})
        self.assertEqual(container.items, {})
        self.assertEqual(self.goods_total(town, npc, (container,)), before)

    def test_other_households_private_tools_are_not_taken(self):
        state, town, npc, equipment = self.make()
        npc.home_id = "house:test"
        container = ContainerState(
            "store:other", 10, 10, 0, "npc:other", 100000, 100000,
            items={"core:iron_pick": 1}, kind="property", settlement_id=town.uid, property_id=npc.home_id,
        )
        state.containers["10,10,0"] = container
        equipment.provision_settlement(town)
        self.assertEqual(npc.inventory, {})
        self.assertEqual(container.items, {"core:iron_pick": 1})

    def test_roundtrip_legacy_defaults_and_invalid_gear_detection(self):
        state, town, npc, equipment = self.make()
        town.stocks["core:iron_pick"] = 1
        equipment.provision_settlement(town)
        restored = LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.npcs[npc.uid].equipment, npc.equipment)
        self.assertEqual(validate_sim_state(restored.to_dict()), [])
        legacy = state.to_dict()
        legacy["npcs"][npc.uid].pop("equipment")
        self.assertEqual(LivingWorldState.from_dict(legacy).npcs[npc.uid].equipment, {})
        broken = state.to_dict()
        broken["npcs"][npc.uid]["inventory"] = {}
        self.assertIn(f"NPC equipment exceeds carried inventory: {npc.uid}", validate_sim_state(broken))
        npc.inventory.clear()
        equipment.reconcile(npc)
        self.assertEqual(npc.equipment, {})

    def test_new_settlement_capital_is_deterministic_and_issued_once(self):
        state, town, npc, equipment = self.make("guard")
        town.stocks.update(starting_equipment_stock([npc], self.registry))
        self.assertEqual(town.stocks, starting_equipment_stock([npc], self.registry))
        total = self.goods_total(town, npc)
        equipment.provision_settlement(town)
        self.assertEqual(self.goods_total(town, npc), total)
        self.assertEqual(len(npc.equipment), 5)
        self.assertTrue(all(count == 1 for count in npc.inventory.values()))

    def test_equipped_representative_save_passes_verify_save_tool(self):
        state, town, npc, equipment = self.make()
        town.stocks.update(starting_equipment_stock([npc], self.registry))
        equipment.provision_settlement(town)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "npc-equipment.db"
            db = WorldDatabase.create(path, "NPC Equipment", b"npc-equipment".hex())
            try:
                db.save_state(turn=0, tile_deltas={}, player_id=1, position=WorldPos(0, 0, 0), inventory={}, sim_state=state.to_dict())
            finally:
                db.close()
            result = subprocess.run(
                [sys.executable, "tools/verify_save.py", str(path)], capture_output=True, text=True, timeout=25,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Save integrity: OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
