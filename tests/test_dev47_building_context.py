"""Separate exterior/door actions and HUD-only aggressive stance selection."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests import test_property_storage_casing
from worldseed.app import _world_context_menu
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.entities.store import EntityStore
from worldseed.systems.property_intrusion import CasingSystem
from worldseed.ui.screens import look_screen


class BuildingContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_property_storage_casing.PropertyStorageCasingTests.setUpClass()

    def fixture(self):
        fixture=test_property_storage_casing.PropertyStorageCasingTests()
        base,security=fixture._security_fixture()
        state,town,physical,*_=base
        door=next(d for d in state.door_security.values() if d.role=='entrance' and d.access!='public')
        door.locked=True
        entities=EntityStore();player=entities.spawn(preferred_id=1)
        entities.add(player,Inventory({'core:lockpick':1}))
        sim=SimpleNamespace(state=state,registry=fixture.registry,
            player_pos=physical.frontage_for(door.property_id),
            interiors=SimpleNamespace(player_presence=lambda:None),
            building=SimpleNamespace(container_at=lambda p:None),
            settlement_physicalization=physical,property_security=security,
            hunting=SimpleNamespace(signs_at=lambda p:[],home_at=lambda p:None),
            casing=SimpleNamespace(intel_for=lambda p:None,can_case=CasingSystem.can_case),
            resources=SimpleNamespace(is_harvestable=lambda p:False),
            fishing=SimpleNamespace(is_fishable=lambda p:False),
            homestead=SimpleNamespace(at=lambda p:None),known_npc_ids=lambda:set())
        return SimpleNamespace(sim=sim,entities=entities,player_id=player),door,physical

    def rows(self,ctx,target):
        found=[]
        def select(term,title,rows,**kwargs):
            found.extend(rows)
            return None
        before=ctx.sim.state.to_dict()
        with patch('worldseed.app._select',side_effect=select):
            _world_context_menu(ctx,object(),target)
        self.assertEqual(ctx.sim.state.to_dict(),before)
        return {key for key,label in found}

    def test_criminal_door_actions_only_in_hud_selected_aggressive_stance(self):
        ctx,door,_=self.fixture()
        target=WorldPos(door.x,door.y,door.z)
        for stance in ('normal','stalk','crouch','aggressive'):
            ctx.sim.state.player_hunting_stance=stance
            rows=self.rows(ctx,target)
            self.assertNotIn('aggressive_stance',rows)
            self.assertIn('enter_interior',rows)
            self.assertEqual('lockpick_property_door' in rows,stance=='aggressive')
            self.assertEqual('force_property_door' in rows,stance=='aggressive')

    def test_body_and_entrance_offer_separate_actions_without_hidden_contents(self):
        ctx,door,physical=self.fixture()
        structure=physical.structure_by_id(door.property_id)
        x,y=next(cell for cell in structure.footprint if cell!=(door.x,door.y))
        body=self.rows(ctx,WorldPos(x,y,door.z))
        entrance=self.rows(ctx,WorldPos(door.x,door.y,door.z))
        self.assertIn('inspect_building_exterior',body)
        self.assertNotIn('enter_interior',body)
        self.assertNotIn('inspect_fixture',body)
        self.assertNotIn('open',body)
        self.assertIn('enter_interior',entrance)
        self.assertNotIn('inspect_building_exterior',entrance)

    def test_exterior_look_never_reads_hidden_storage_actors_or_terrain(self):
        ctx,door,physical=self.fixture()
        # The fixture deliberately has no world/skill APIs. Looking at a shell
        # can expose only the prepared exterior, not inspect its old room cells.
        before=ctx.sim.state.to_dict()
        text=look_screen(ctx.sim,80,WorldPos(door.x,door.y,door.z))
        self.assertIn('Entrance door',text)
        self.assertNotIn('Storage:',text)
        self.assertEqual(ctx.sim.state.to_dict(),before)


if __name__=='__main__':unittest.main()
