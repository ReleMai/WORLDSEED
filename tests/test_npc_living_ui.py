from types import SimpleNamespace
import unittest

from worldseed.app import _npc_profile_data, _npc_profile_menu
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.systems.state import LivingWorldState, NPCState
from worldseed.systems.npc_schedule import schedule_at, schedule_rows
from worldseed.ui.npc_activity import activity_label, schedule_label, timeline_rows
from worldseed.ui.screens import npc_detail_screen


class LivingNPCUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def fixture(self):
        state=LivingWorldState()
        npc=NPCState('npc:test','Eda',35,'farmer',[],4,7,0,'','',wealth=37)
        state.npcs[npc.uid]=npc
        state.discovered_npcs=[npc.uid];state.introduced_npcs=[npc.uid]
        sim=SimpleNamespace(state=state,registry=self.registry,seed=b'living-ui',
                            known_npc_ids=lambda:set(state.discovered_npcs),
                            known_settlement_ids=lambda:set(),
                            settlement_physicalization=SimpleNamespace(structure_by_id=lambda _:None))
        return sim,npc

    def test_profile_reads_actual_equipment_cash_and_task_without_mutating(self):
        sim,npc=self.fixture()
        clothing=next(i for i in self.registry.items.values() if i.equip_slot)
        npc.inventory={clothing.id:2,'core:wood':3}
        npc.tasks=[{'kind':'move','x':12,'y':9,'z':0}]
        before=sim.state.to_dict()
        data=_npc_profile_data(sim,npc,'belongings')
        self.assertEqual(data['summary']['activity'],'Walking — work')
        self.assertEqual(data['tabs']['appearance'][0][1],'No identifiable equipment')
        self.assertIn(('Carried cash','37c'),data['tabs']['belongings'])
        self.assertIn((clothing.name,'2'),data['tabs']['belongings'])
        self.assertEqual(before,sim.state.to_dict())
        npc.equipment['body']=clothing.id
        data=_npc_profile_data(sim,npc,'appearance')
        self.assertIn(clothing.name,data['tabs']['appearance'][0][1])
        self.assertEqual(npc.inventory[clothing.id],2)

    def test_unknown_person_does_not_reveal_private_belongings(self):
        sim,npc=self.fixture();sim.state.introduced_npcs=[]
        data=_npc_profile_data(sim,npc,'overview')
        self.assertNotIn('belongings',data['tabs'])
        self.assertNotIn('37c',str(data))
        self.assertEqual(data['summary']['name'],'Stranger')
        self.assertNotIn('schedule',data['summary'])
        self.assertNotIn('Personal timeline',str(data))

    def test_personal_timeline_matches_simulation_and_is_observational(self):
        sim,npc=self.fixture()
        sim.state.clock_minute=9*60
        before=sim.state.to_dict()
        expected_rows=schedule_rows(npc,sim.seed)
        current=schedule_at(npc,sim.seed,sim.state.clock_minute)
        self.assertEqual(timeline_rows(npc,sim.seed),expected_rows)
        self.assertIn(current.label,schedule_label(npc,sim.seed,sim.state.clock_minute))
        profile=_npc_profile_data(sim,npc,'overview')
        for row in expected_rows:
            self.assertIn(row,profile['tabs']['overview'])
        self.assertIn(current.label,profile['summary']['schedule'])
        detail=npc_detail_screen(sim,npc.uid,width=112)
        self.assertIn('PERSONAL TIMELINE',detail)
        for time_range,label in expected_rows:
            self.assertIn(time_range,detail)
            self.assertIn(label,detail)
        self.assertEqual(before,sim.state.to_dict())

    def test_world_console_does_not_expose_an_unknown_person_timeline(self):
        sim,npc=self.fixture();sim.state.discovered_npcs=[]
        before=sim.state.to_dict()
        detail=npc_detail_screen(sim,npc.uid,width=80)
        self.assertIn('not learned',detail)
        self.assertNotIn('PERSONAL TIMELINE',detail)
        self.assertEqual(before,sim.state.to_dict())

    def test_activity_label_uses_current_action_instead_of_old_goal(self):
        _,npc=self.fixture();npc.goal='work'
        npc.tasks=[{'kind':'perform','action':'drink'}]
        self.assertEqual(activity_label(npc),'Drink')

    def test_trade_labels_are_observational(self):
        sim,npc=self.fixture()
        npc.tasks=[{'kind':'perform','action':'commerce_sell','items':{'core:wood':2}}]
        before=sim.state.to_dict()
        self.assertEqual(activity_label(npc),'Selling goods')
        self.assertEqual(before,sim.state.to_dict())

    def test_belongings_page_returns_to_selected_profile_tab_on_escape(self):
        sim,npc=self.fixture()
        npc.inventory={iid:1 for iid in list(self.registry.items)[:35]}
        class Term:
            mouse_ui=False
            def __init__(self):self.keys=iter(['3','PGDN','ESC','ESC']);self.frames=[]
            def size(self):return (80,14)
            def present(self,text):self.frames.append(text)
            def read_key(self):return next(self.keys)
        term=Term();before=sim.state.to_dict()
        _npc_profile_menu(SimpleNamespace(sim=sim),term,npc.uid)
        self.assertIn('Cash / Gear / Pack',term.frames[0])
        self.assertIn('Carried cash',term.frames[1])
        self.assertNotIn('Carried cash',term.frames[2])
        self.assertIn('> 3. Cash / Gear / Pack',term.frames[-1])
        self.assertEqual(before,sim.state.to_dict())
