import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.sim.commands import BarterCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.ai import NPCSystem
from worldseed.systems.economy import EconomySystem
from worldseed.systems.state import CultureState, LivingWorldState, NPCState, SettlementState


class NullHistory:
    def record(self,*args,**kwargs):
        pass


def make_town(uid='settlement:economy'):
    return SettlementState(
        uid=uid,name='Ledger Town',region_x=0,region_y=0,x=0,y=0,population=80,
        culture_id='culture:ledger',religion_id='religion:test',faction_id='faction:ledger',
        stocks={
            'core:wheat':160,'core:turnip':100,'core:wood':100,'core:stone':100,
            'core:iron_ore':50,'core:coal':50,'core:medicinal_herb':30,
        },
        knowledge=['tech:smelting','knowledge:herbalism','knowledge:literacy'],
    )


class EconomyRoutineTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def _economy(self):
        state=LivingWorldState()
        town=make_town()
        state.settlements[town.uid]=town
        state.cultures[town.culture_id]=CultureState(
            town.culture_id,'Ledgerfolk',['trade'],'short',[],'metal'
        )
        economy=EconomySystem(state,self.registry,b'ledger-test',NullHistory())
        economy.update_prices()
        return state,town,economy

    def test_named_worker_binds_to_daily_labor_without_duplicate_output(self):
        state,town,economy=self._economy()
        npc=NPCState(
            uid='npc:farmer',name='Farmer',age=34,occupation='farmer',
            traits=['patient'],x=0,y=0,z=0,settlement_id=town.uid,
            faction_id=town.faction_id,workplace_id='structure:mill',
        )
        state.npcs[npc.uid]=npc
        assignments=economy._reserve_labor(town,3)
        self.assertTrue(assignments)
        self.assertTrue(npc.assigned_process_id)
        reservation=state.labor_reservations[f'labor:{town.uid}:{npc.assigned_process_id}']
        self.assertIn(npc.uid,reservation.representative_uids)
        before=dict(town.stocks)
        ai=NPCSystem(state,b'ledger-test',NullHistory())
        ai.attach_economy(economy)
        ai._work(npc,town,3*1440+9*60)
        self.assertEqual(before,town.stocks)
        self.assertEqual(npc.work_hours_today,1)

    def test_routine_bias_tracks_work_meals_sleep_and_guard_shifts(self):
        state,town,economy=self._economy()
        npc=NPCState(
            uid='npc:merchant',name='Merchant',age=33,occupation='merchant',
            traits=['kind'],x=0,y=0,z=0,settlement_id=town.uid,
            faction_id=town.faction_id,
        )
        ai=NPCSystem(state,b'routine-test',NullHistory())
        self.assertGreater(ai._routine_bias(npc,10*60)['work'],0)
        self.assertGreater(ai._routine_bias(npc,18*60)['eat'],0)
        self.assertGreater(ai._routine_bias(npc,23*60)['rest'],0)
        guard=NPCState(
            uid='npc:guard',name='Guard',age=30,occupation='guard',
            traits=[],x=0,y=0,z=0,settlement_id=town.uid,faction_id=town.faction_id,
        )
        active=sum(1 for hour in range(24) if ai._routine_bias(guard,hour*60)['guard']>0)
        self.assertEqual(active,8)

    def test_market_transactions_are_persistent_bounded_economic_events(self):
        state,town,economy=self._economy()
        row=economy.record_transaction(
            town.uid,'player_barter','player',town.uid,copper_value=12,minute=600,
            offered={'core:wood':3},requested={'core:wheat':2},
        )
        self.assertEqual(row.currency_id,town.currency_id)
        self.assertEqual(row.offered,{'core:wood':3})
        self.assertEqual(row.requested,{'core:wheat':2})
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertIn(row.uid,restored.market_transactions)
        self.assertEqual(restored.market_transactions[row.uid].copper_value,12)

    def test_simulation_barter_moves_goods_without_minting_coin(self):
        state,town,economy=self._economy()
        town.stocks['core:wheat']=50
        inv=Inventory()
        inv.add('core:wood',20)
        inv.add('core:copper_coin',7)

        class Harness:
            pass
        sim=Harness()
        sim.state=state
        sim.registry=self.registry
        sim.economy=economy
        sim.clock=SimpleNamespace(minute=720)
        sim.player_pos=WorldPos(0,0,0)
        sim.entities=SimpleNamespace(get=lambda actor,typ:inv)
        sim.messages=[]
        sim._message=lambda message:sim.messages.append(message)
        sim.player_trade_price=lambda settlement_id,item_id,buy:economy.trade_price(settlement_id,item_id,buy)
        sim.player_barter_value=lambda settlement_id,goods,offered:sum(
            sim.player_trade_price(settlement_id,iid,not offered)*qty for iid,qty in goods.items()
        )
        sim.player_barter_balance=lambda settlement_id,offered,requested:(
            sim.player_barter_value(settlement_id,offered,True)-
            sim.player_barter_value(settlement_id,requested,False)
        )

        before_coin=inv.count('core:copper_coin')
        # Pick enough wood to exceed the requested wheat value under local prices.
        offered=10
        requested=1
        Simulation._barter(
            sim,BarterCommand(1,town.uid,'core:wood',offered,'core:wheat',requested)
        )
        self.assertEqual(inv.count('core:copper_coin'),before_coin)
        self.assertEqual(inv.count('core:wood'),20-offered)
        self.assertEqual(inv.count('core:wheat'),requested)
        self.assertTrue(any(row.kind=='player_barter' for row in state.market_transactions.values()))

    def test_family_social_choice_prefers_kin(self):
        state,town,economy=self._economy()
        npc=NPCState(
            uid='npc:a',name='A',age=30,occupation='merchant',traits=['kind'],
            x=0,y=0,z=0,settlement_id=town.uid,faction_id=town.faction_id,
            spouse_uid='npc:b',home_id='home:a',home_room_id='room:a',
            workplace_id='market:a',needs={'social':90,'safety':0,'health':0,'faith':0,'learning':0,'purpose':0},
        )
        spouse=NPCState(
            uid='npc:b',name='B',age=31,occupation='healer',traits=[],
            x=1,y=0,z=0,settlement_id=town.uid,faction_id=town.faction_id,
        )
        stranger=NPCState(
            uid='npc:c',name='C',age=31,occupation='smith',traits=[],
            x=2,y=0,z=0,settlement_id=town.uid,faction_id=town.faction_id,
        )
        state.npcs={n.uid:n for n in (npc,spouse,stranger)}
        ai=NPCSystem(state,b'social-test',NullHistory())
        ai.settlement_physicalization=SimpleNamespace(
            destination_for=lambda sid,rid:WorldPos(5,5,0),
            destination_for_function=lambda sid,functions:WorldPos(9,9,0),
        )
        npc.hunger=npc.thirst=npc.rest=0
        ai._choose_goal_and_plan(npc,town,19*60)
        self.assertEqual(npc.goal,'socialize')
        self.assertEqual(npc.tasks[-1].get('target'),spouse.uid)
        self.assertEqual((npc.tasks[0]['x'],npc.tasks[0]['y']),(5,5))


if __name__=='__main__':
    unittest.main()
