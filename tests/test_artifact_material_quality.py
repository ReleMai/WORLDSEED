"""Material quality participates in real damage, wear and market transfers."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.persistence.validation import validate_sim_state
from worldseed.sim.commands import BarterCommand, BuyCommand, DropCommand, SellCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.artifacts import ArtifactSystem, crafting_effects
from worldseed.systems.combat import CombatSystem
from worldseed.systems.state import CreatureState, LivingWorldState, SettlementState


class CraftedArtifactQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.registry=ContentRegistry.load(DATA_DIR)

    def make(self,quality=80,item_id='core:iron_sword',state=None,owner='player'):
        state=state or LivingWorldState()
        system=ArtifactSystem(state,self.registry,b'material-quality')
        item=self.registry.items[item_id]
        artifact=system.create(item_id,'maker',100,quality_hint=quality,owner=owner,
                               components_override={'body':{'material':item.material or 'core:iron','quality':quality,'condition':100},
                                                    'crafting':{'quality_version':1,'material_quality':quality,'inputs':{'core:metal_scraps':2}}})
        return state,system,artifact

    def test_opted_in_quality_is_exact_monotonic_and_metadata_does_not_alias(self):
        state=LivingWorldState();system=ArtifactSystem(state,self.registry,b'quality-exact')
        components={'body':{'material':'core:iron','quality':30,'condition':100},'crafting':{'quality_version':1}}
        for quality in range(101):
            components['body']['quality']=quality
            artifact=system.create('core:iron_sword','maker',quality,quality_hint=quality,components_override=components)
            self.assertEqual(artifact.quality,quality)
        components['body']['quality']=999
        self.assertEqual(state.artifacts['artifact:1'].components['body']['quality'],0)
        self.assertEqual(state.artifacts['artifact:101'].components['body']['quality'],100)

    def test_legacy_quality_randomness_wear_and_value_stay_unchanged(self):
        state=LivingWorldState();system=ArtifactSystem(state,self.registry,b'legacy-quality')
        qualities=set()
        for minute in range(20):
            artifact=system.create('core:iron_sword','maker',minute,quality_hint=80)
            qualities.add(artifact.quality)
            self.assertTrue(75<=artifact.quality<=85)
        self.assertGreater(len(qualities),1)
        artifact=system.best_owned('core:iron_sword')
        before=artifact.condition
        system.wear('core:iron_sword','player',3,25)
        self.assertEqual(artifact.condition,before-3)
        self.assertEqual(system.describe_effects(artifact)['value_percent'],100)
        self.assertEqual(system.describe_effects(artifact)['wear_rate_percent'],100)
        self.assertEqual(system.trade_quote('core:iron_sword','player',2,100)[0],200)

    def test_fractional_wear_accumulates_and_better_material_last_longer(self):
        conditions=[]
        for quality in (20,80):
            state,system,artifact=self.make(quality)
            for minute in range(30):system.wear(artifact.base_item,'player',1,minute)
            conditions.append(artifact.condition)
            self.assertLess(artifact.condition,100)
            self.assertLess(artifact.components['crafting']['wear_remainder'],50+quality)
        self.assertGreater(conditions[1],conditions[0])

    def test_fractional_wear_roundtrip_resumes_exactly_and_effects_are_observational(self):
        state,system,artifact=self.make()
        system.wear(artifact.base_item,'player',1,101)
        restored=LivingWorldState.from_dict(state.to_dict())
        other=ArtifactSystem(restored,self.registry,b'material-quality')
        before=deepcopy(state.to_dict())
        effects=system.describe_effects(artifact)
        self.assertEqual(effects['damage_percent'],crafting_effects(self.registry.items[artifact.base_item],artifact.quality)['damage_percent'])
        system.trade_quote(artifact.base_item,'player',1,100)
        self.assertEqual(state.to_dict(),before)
        for minute in range(102,131):
            system.wear(artifact.base_item,'player',1,minute)
            other.wear(artifact.base_item,'player',1,minute)
        self.assertEqual(restored.artifacts[artifact.uid].condition,artifact.condition)
        self.assertEqual(restored.artifacts[artifact.uid].components,artifact.components)
        self.assertEqual(validate_sim_state(restored.to_dict()),[])

    def test_actual_melee_damage_increases_with_material_quality(self):
        damages=[]
        for quality in (20,80):
            state,system,artifact=self.make(quality)
            combat=CombatSystem(state,self.registry,b'quality-combat',system)
            state.player_readied_weapon=artifact.base_item
            inv=Inventory({artifact.base_item:1})
            species=next(iter(self.registry.species))
            creature=CreatureState('creature:quality',species,0,0,0,100000,blood=100000)
            state.creatures[creature.uid]=creature
            for minute in range(12):combat.attack_creature(creature,inv,minute)
            damages.append(100000-creature.hp)
        self.assertGreater(damages[0],0)
        self.assertGreater(damages[1],damages[0])

    def test_actual_short_bow_damage_uses_preview_quality_and_legacy_stays_unchanged(self):
        totals=[]
        for marked,quality in ((True,20),(True,80),(False,20),(False,80)):
            state,system,artifact=self.make(quality,'core:short_bow')
            if not marked:artifact.components.pop('crafting')
            combat=CombatSystem(state,self.registry,b'quality-ranged',system)
            state.player_readied_weapon=artifact.base_item
            inv=Inventory({artifact.base_item:1,'core:wood_arrow':30})
            species=next(iter(self.registry.species))
            creature=CreatureState('creature:quality-ranged',species,0,0,0,100000,blood=100000)
            state.creatures[creature.uid]=creature
            for turn in range(20):
                combat.ranged_attack_creature(creature,inv,turn,2,perception=20,hunting=0,aim_quality=100)
            totals.append(100000-creature.hp)
            self.assertGreater(totals[-1],0)
            self.assertEqual(inv.count('core:wood_arrow'),10)
        self.assertGreater(totals[1],totals[0])
        self.assertEqual(totals[2],totals[3])
        effects=crafting_effects(self.registry.items['core:short_bow'],80)
        self.assertEqual(effects['damage_multiplier'],1.6)

    def test_marked_bow_wears_on_fired_misses_better_quality_lasts_longer_and_legacy_does_not_wear(self):
        shot_counts=[]
        for quality in (20,80):
            state,system,artifact=self.make(quality,'core:short_bow')
            combat=CombatSystem(state,self.registry,b'quality-bow-wear',system)
            state.player_readied_weapon=artifact.base_item
            inv=Inventory({artifact.base_item:1,'core:wood_arrow':200})
            species=next(iter(self.registry.species))
            creature=CreatureState('creature:bow-wear',species,0,0,0,100000,blood=100000)
            state.creatures[creature.uid]=creature
            misses=0
            for turn in range(200):
                if inv.count(artifact.base_item)<=0:break
                message=combat.ranged_attack_creature(creature,inv,turn,2,cover_penalty=1000)
                misses += 'misses' in message
            shots=200-inv.count('core:wood_arrow');shot_counts.append(shots)
            self.assertGreater(misses,0)
            self.assertEqual(artifact.condition,0)
            self.assertEqual(artifact.owner,'destroyed')
            self.assertEqual(state.player_readied_weapon,'')
        self.assertEqual(shot_counts,[70,130])
        state,system,artifact=self.make(80,'core:short_bow')
        artifact.components.pop('crafting')
        combat=CombatSystem(state,self.registry,b'quality-bow-legacy',system)
        inv=Inventory({artifact.base_item:1,'core:wood_arrow':5})
        creature=CreatureState('creature:legacy-bow',next(iter(self.registry.species)),0,0,0,100000,blood=100000)
        for turn in range(5):combat.ranged_attack_creature(creature,inv,turn,2,weapon_id=artifact.base_item)
        self.assertEqual(artifact.condition,100)
        # An unsuccessful firing precondition consumes neither arrow nor condition.
        before=artifact.condition,dict(inv.items)
        combat.ranged_attack_creature(creature,inv,6,2,weapon_id=artifact.base_item)
        self.assertEqual((artifact.condition,inv.items),before)

    def test_exact_equipped_armor_and_shield_use_quality_durability(self):
        armor=next(item for item in self.registry.items.values() if item.armor>0 and 'torso' in item.coverage and item.equip_slot)
        shield=next(item for item in self.registry.items.values() if 'shield' in item.tags)
        for item,slot,kind in ((armor,armor.equip_slot,'armor'),(shield,'offhand','shield')):
            conditions=[]
            for quality in (20,80):
                state,system,artifact=self.make(quality,item.id)
                state.player_equipment[slot]=item.id
                state.player_equipped_artifacts[slot]=artifact.uid
                combat=CombatSystem(state,self.registry,b'quality-defend',system)
                vitals=Vitals(hp=100000,blood=100000)
                for minute in range(20):
                    if kind=='armor':combat.resolve_player_hit(vitals,'torso',16,'blunt','melee',minute)
                    else:combat.shield_defend(20,'torso','melee','blunt',minute,source_dy=1)
                conditions.append(artifact.condition)
                self.assertLess(artifact.condition,100)
            self.assertGreater(conditions[1],conditions[0],kind)


class QualityMarketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.registry=ContentRegistry.load(DATA_DIR)

    def make(self):
        class Harness:
            _player_trade_quote=Simulation._player_trade_quote
            player_trade_price=Simulation.player_trade_price
            player_trade_total=Simulation.player_trade_total
            player_barter_value=Simulation.player_barter_value
            player_barter_balance=Simulation.player_barter_balance
            _buy=Simulation._buy
            _sell=Simulation._sell
            _barter=Simulation._barter
        sim=Harness();state=LivingWorldState();inv=Inventory({'core:copper_coin':10000})
        town=SettlementState('settlement:quality','Quality Market',0,0,0,0,50,'culture:test','religion:test','faction:test',wealth=10000)
        state.settlements[town.uid]=town
        sim.state=state;sim.registry=self.registry;sim.player_pos=WorldPos(0,0,0)
        sim.entities=SimpleNamespace(get=lambda actor,kind:inv)
        sim.clock=SimpleNamespace(minute=100)
        sim.player_skill=lambda skill:0;sim.has_talent=lambda talent:False
        sim.artifacts=ArtifactSystem(state,self.registry,b'quality-trade')
        sim.metallurgy=SimpleNamespace(transfer_one=lambda *args:None)
        sim.transactions=[];sim.messages=[]
        sim.economy=SimpleNamespace(trade_price=lambda town,iid,buy:100 if buy else 80,
                                    update_prices=lambda:None,
                                    record_transaction=lambda *args,**kwargs:sim.transactions.append(kwargs))
        sim._message=sim.messages.append
        return sim,state,inv,town

    def artifact(self,sim,quality,owner='player',item_id='core:iron_sword'):
        item=self.registry.items[item_id]
        return sim.artifacts.create(item_id,'maker',100,quality_hint=quality,owner=owner,
                                    components_override={'body':{'material':item.material or 'core:iron','quality':quality,'condition':100},
                                                         'crafting':{'quality_version':1}})

    def test_sell_handler_pays_quality_value_and_transfers_that_exact_uid(self):
        revenues=[]
        for quality in (20,80):
            sim,state,inv,town=self.make();artifact=self.artifact(sim,quality)
            inv.add(artifact.base_item,1)
            quote=sim.player_trade_total(town.uid,artifact.base_item,False,1)
            before_coin=inv.count('core:copper_coin');before_wealth=town.wealth
            sim._sell(SellCommand(1,town.uid,artifact.base_item))
            revenue=inv.count('core:copper_coin')-before_coin;revenues.append(revenue)
            self.assertEqual(revenue,quote)
            self.assertEqual(town.wealth,before_wealth-revenue)
            self.assertEqual(inv.count(artifact.base_item),0)
            self.assertEqual(artifact.owner,town.uid)
            self.assertEqual(sim.transactions[-1]['copper_value'],revenue)
        self.assertGreater(revenues[1],revenues[0])

    def test_mixed_stack_quote_matches_payment_and_skips_equipped_instance(self):
        sim,state,inv,town=self.make()
        equipped=self.artifact(sim,100)
        state.player_equipped_artifacts['mainhand']=equipped.uid
        state.player_equipment['mainhand']=equipped.base_item # Equipped physical unit is outside Inventory.
        low=self.artifact(sim,20);high=self.artifact(sim,80)
        inv.add(low.base_item,3) # Two instance items plus one ordinary commodity.
        quote=sim.player_trade_total(town.uid,low.base_item,False,3)
        self.assertEqual(quote,56+104+80)
        before=inv.count('core:copper_coin')
        sim._sell(SellCommand(1,town.uid,low.base_item,3))
        self.assertEqual(inv.count('core:copper_coin')-before,quote)
        self.assertEqual(equipped.owner,'player')
        self.assertEqual(low.owner,town.uid);self.assertEqual(high.owner,town.uid)

    def test_buy_and_resell_same_instance_use_quality_on_both_sides(self):
        sim,state,inv,town=self.make();artifact=self.artifact(sim,80,town.uid)
        town.stocks[artifact.base_item]=1
        buy=sim.player_trade_total(town.uid,artifact.base_item,True,1)
        before=inv.count('core:copper_coin')
        sim._buy(BuyCommand(1,town.uid,artifact.base_item))
        self.assertEqual(inv.count('core:copper_coin'),before-buy)
        self.assertEqual(artifact.owner,'player')
        sell=sim.player_trade_total(town.uid,artifact.base_item,False,1)
        sim._sell(SellCommand(1,town.uid,artifact.base_item))
        self.assertEqual(inv.count('core:copper_coin'),before-buy+sell)
        self.assertLess(sell,buy)
        self.assertEqual(artifact.owner,town.uid)

    def test_damage_decreases_real_sale_quote_and_insufficient_coin_changes_nothing(self):
        sim,state,inv,town=self.make();artifact=self.artifact(sim,80)
        inv.add(artifact.base_item,1)
        full=sim.player_trade_price(town.uid,artifact.base_item,False)
        artifact.condition=30
        self.assertLess(sim.player_trade_price(town.uid,artifact.base_item,False),full)
        town.wealth=0;before=state.to_dict(),dict(inv.items)
        sim._sell(SellCommand(1,town.uid,artifact.base_item))
        self.assertEqual((state.to_dict(),inv.items),before)
        self.assertEqual(sim.transactions,[])

    def test_barter_transfers_instances_without_minting_coin_or_duplicate_ownership(self):
        sim,state,inv,town=self.make()
        offered=self.artifact(sim,100)
        requested=self.artifact(sim,20,town.uid,'core:iron_helmet')
        inv.add(offered.base_item,1);town.stocks[requested.base_item]=1
        before=inv.count('core:copper_coin'),town.wealth
        sim._barter(BarterCommand(1,town.uid,offered.base_item,1,requested.base_item,1))
        self.assertEqual(offered.owner,town.uid)
        self.assertEqual(requested.owner,'player')
        self.assertEqual((inv.count('core:copper_coin'),town.wealth),before)
        self.assertEqual(inv.count(offered.base_item),0)
        self.assertEqual(inv.count(requested.base_item),1)
        self.assertEqual(sim.transactions[-1]['copper_value'],70)

    def test_sale_and_drop_reject_the_last_protected_instance_without_mutation(self):
        for has_physical_slot in (False,True):
            for drop in (False,True):
                with self.subTest(slot=has_physical_slot,drop=drop):
                    sim,state,inv,town=self.make()
                    artifact=self.artifact(sim,80,item_id='core:iron_helmet')
                    state.player_equipped_artifacts['head']=artifact.uid
                    if has_physical_slot:state.player_equipment['head']=artifact.base_item
                    else:inv.add(artifact.base_item,1) # Legacy/map-only protected unit still in stack.
                    sim.entities=SimpleNamespace(get=lambda actor,kind:SimpleNamespace(value=sim.player_pos) if kind is Position else inv)
                    before=state.to_dict(),dict(inv.items)
                    if drop:Simulation._drop(sim,DropCommand(1,artifact.base_item))
                    else:sim._sell(SellCommand(1,town.uid,artifact.base_item))
                    self.assertEqual((state.to_dict(),inv.items),before)
                    self.assertEqual(artifact.owner,'player')

    def test_nonpositive_buy_and_sell_do_not_change_stocks_money_or_instances(self):
        for command_type in (BuyCommand,SellCommand):
            for amount in (0,-1):
                sim,state,inv,town=self.make();artifact=self.artifact(sim,80)
                inv.add(artifact.base_item,1);town.stocks[artifact.base_item]=1
                before=state.to_dict(),dict(inv.items)
                handler=sim._buy if command_type is BuyCommand else sim._sell
                handler(command_type(1,town.uid,artifact.base_item,amount))
                self.assertEqual((state.to_dict(),inv.items),before)
                self.assertEqual(sim.transactions,[])


if __name__=='__main__':unittest.main()
