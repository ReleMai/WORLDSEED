"""Salvage content enters real, persistent goods authorities exactly once."""
import unittest
from types import SimpleNamespace

from tests import test_property_storage_casing as property_fixtures
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.systems.building import BuildingSystem
from worldseed.systems.container_profiles import catalog
from worldseed.systems.dungeons import DungeonSystem
from worldseed.systems.processing import ProcessingSystem
from worldseed.systems.resources import FeatureView, ResourceSystem
from worldseed.systems.salvage_loot import (
    BUILDING_CONTEXTS, PROFILE_CONTEXTS, candidates, misc_catalog,
    provision_village, select_misc, withdraw_misc,
)
from worldseed.systems.state import (
    CarcassState, ContainerState, DungeonSiteState, LivingWorldState, pos_key,
)


class SalvageLootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def test_every_misc_item_has_a_real_contextual_acquisition_path(self):
        rows=misc_catalog()
        self.assertGreater(len(rows),200)
        profiles=catalog()[0]
        for row in rows:
            iid=row['item_id']
            self.assertIn(iid,self.registry.items)
            if row['source']=='village':
                matches=[profile for uid,profile in profiles.items()
                         if set(PROFILE_CONTEXTS.get(uid,())).intersection(row['loot_contexts'])]
                self.assertTrue(matches,iid)
                self.assertTrue(any(iid in profile.loot for profile in matches),iid)
                self.assertTrue(any(set(contexts).intersection(row['loot_contexts'])
                                    for contexts in BUILDING_CONTEXTS.values()),iid)
            elif row['source']=='wild':
                feature=self.registry.resources['core:salvage_patch_'+iid.split(':',1)[-1]]
                self.assertIn(iid,feature.yields)
                self.assertEqual(set(feature.terrains),set(row['habitats']))
                self.assertTrue(feature.regrow_days)
                self.assertTrue(all(t in self.registry.terrains for t in feature.terrains))
                if row['rarity']=='rare':
                    self.assertIn('rare_flora',feature.tags)
                    self.assertTrue(any(iid in recipe.inputs for recipe in self.registry.recipes.values()),iid)
            else:
                self.assertTrue(row['species'],iid)
                for sid in row['species']:
                    self.assertGreater(self.registry.species[sid].carcass.get(iid,0),0)
                    self.assertNotIn(iid,self.registry.species[sid].drops)

    def test_initial_village_goods_are_bounded_order_independent_and_saved(self):
        structures=[SimpleNamespace(uid='house:a',function='residence',destroyed=False),
                    SimpleNamespace(uid='smith:b',function='smithy',destroyed=False)]
        states=[]
        for order in (structures,list(reversed(structures))):
            state=LivingWorldState();town=SimpleNamespace(uid='town:test',stocks={})
            self.assertEqual(provision_village(state,self.registry,b'loot-test',town,order),16)
            before=dict(town.stocks)
            self.assertEqual(provision_village(state,self.registry,b'loot-test',town,order),0)
            restored=LivingWorldState.from_dict(state.to_dict())
            self.assertEqual(provision_village(restored,self.registry,b'loot-test',town,order),0)
            self.assertEqual(town.stocks,before)
            states.append((town.stocks,state.resource_depletion))
        self.assertEqual(states[0],states[1])

    def test_storage_transfer_conserves_goods_and_never_refills_taken_items(self):
        state=LivingWorldState();rows=candidates(self.registry,('household',),source='village')
        town=SimpleNamespace(uid='town',stocks={row['item_id']:3 for row in rows})
        container=ContainerState('real:chest',0,0,0,'town',100000,100000,
                                 profile_id='core:household_chest',settlement_id='town')
        before=sum(town.stocks.values())
        self.assertGreater(withdraw_misc(state,self.registry,b'loot-test',town,container),0)
        self.assertEqual(sum(town.stocks.values())+sum(container.items.values()),before)
        carried=Inventory();building=BuildingSystem(state,self.registry)
        for iid,n in list(container.items.items()):
            self.assertTrue(building.take(container,carried,iid,n)[0])
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(withdraw_misc(restored,self.registry,b'loot-test',town,container),0)
        self.assertFalse(container.items)
        self.assertEqual(sum(town.stocks.values())+sum(carried.items.values()),before)

    def test_real_property_containers_tabletops_and_ground_project_existing_stock(self):
        property_fixtures.PropertyStorageCasingTests.setUpClass()
        fixture=property_fixtures.PropertyStorageCasingTests()._fixture()
        state,town,physical,_,_,_,storage,_,_,_,_=fixture
        tables=[c for c in state.containers.values() if c.profile_id=='core:tabletop']
        self.assertTrue(tables)
        self.assertTrue(any(c.items for c in tables))
        village_ids={row['item_id'] for row in misc_catalog() if row['source']=='village'}
        self.assertTrue(any(village_ids.intersection(c.items) for c in state.containers.values()))
        self.assertTrue(any(village_ids.intersection(p.items) for p in state.ground_piles.values()))
        before=state.to_dict()
        storage.sync_active()
        self.assertEqual(state.to_dict(),before)
        # Collection removes real pile goods. Its stable parcel origin cannot
        # mint a second batch after saved generated-plan caches are rebuilt.
        state.ground_piles.clear()
        stock_before=dict(town.stocks)
        storage.sync_active()
        self.assertFalse(state.ground_piles)
        self.assertEqual(town.stocks,stock_before)

    def _wild_fixture(self,version=5,terrain_id='core:grass'):
        terrain=self.registry.terrains[terrain_id]
        fields=SimpleNamespace(temperature=30000,moisture=40000,fertility=40000)
        world=SimpleNamespace(tile_at=lambda pos:SimpleNamespace(terrain_id=terrain_id,terrain=terrain),
                              generator=SimpleNamespace(sample_fields=lambda pos:fields),
                              delta_source=SimpleNamespace())
        state=LivingWorldState();resources=ResourceSystem(state,self.registry,b'wild-loot-test',world,version)
        # The test exercises loose-goods realization without competition from
        # unrelated trees or boulders; habitat/climate selection stays real.
        resources.blocks_movement=lambda pos:False
        building=BuildingSystem(state,self.registry);building.attach_resources(resources,b'wild-loot-test')
        return state,resources,building,world

    def test_wild_loose_items_keep_collection_history_through_save_and_cleanup(self):
        state,resources,building,_=self._wild_fixture()
        placed=None
        for x in range(2000):
            pos=WorldPos(x,0,0)
            pile=building.materialize_salvage_ground_at(pos)
            if pile:
                placed=(pos,pile);break
        self.assertIsNotNone(placed)
        pos,pile=placed;before=dict(pile.items)
        for iid in before:
            row=next(row for row in misc_catalog() if row['item_id']==iid)
            self.assertIn('core:grass',row['habitats'])
        state.ground_piles.pop(pos_key(pos.x,pos.y,pos.z))
        resources.cleanup_regrown(365*1440)
        restored=LivingWorldState.from_dict(state.to_dict())
        resources.state=restored;building.state=restored
        self.assertIsNone(building.materialize_salvage_ground_at(pos))
        self.assertFalse(restored.ground_piles)
        old,_,old_building,_=self._wild_fixture(version=4)
        self.assertIsNone(old_building.materialize_salvage_ground_at(pos))
        self.assertFalse(old.ground_piles)

    def test_legacy_resource_versions_keep_exact_base_placement(self):
        for version in (1,2,3,4):
            state,resources,_,world=self._wild_fixture(version)
            legacy_registry=SimpleNamespace(
                terrains=self.registry.terrains,
                resources={iid:f for iid,f in self.registry.resources.items() if 'salvage_expansion' not in f.tags},
            )
            legacy=ResourceSystem(state,legacy_registry,b'wild-loot-test',world,version)
            for tid in ('core:grass','core:forest','core:rock','core:wetland'):
                baseline=[legacy._raw_feature(x,y,tid,'summer') for y in range(5) for x in range(16)]
                current=[resources._raw_feature(x,y,tid,'summer') for y in range(5) for x in range(16)]
                self.assertEqual(current,baseline,(version,tid))

    def test_dungeon_misc_is_deterministic_and_not_reseeded(self):
        snapshots=[]
        for _ in range(2):
            state=LivingWorldState()
            site=DungeonSiteState('site:old','Old Site',0,0,-1,0)
            dungeon=DungeonSystem(state,self.registry,b'dungeon-loot-test',None,None)
            dungeon._seed_loot(site,[(2,3),(5,8)],0,0,0)
            misc={row['item_id'] for row in misc_catalog() if 'dungeon' in row['loot_contexts']}
            self.assertTrue(any(misc.intersection(p.items) for p in state.ground_piles.values()))
            snapshots.append(state.to_dict()['ground_piles'])
            state.ground_piles.clear()
            dungeon._seed_loot(site,[(2,3),(5,8)],0,0,0)
            self.assertFalse(state.ground_piles)
        self.assertEqual(*snapshots)

    def test_all_natural_container_families_have_misc_without_origin_duplication(self):
        misc={row['item_id'] for row in misc_catalog()}
        for fid in ('core:hollow_log_cache','core:rotten_stump_cache','core:rock_crevice_cache'):
            state=LivingWorldState();building=BuildingSystem(state,self.registry)
            resources=SimpleNamespace(feature_at=lambda pos:FeatureView(fid,'mature'),revision=0)
            building.attach_resources(resources,b'natural-loot-test')
            pos=WorldPos(2,3,0)
            container=building.materialize_natural_container_at(pos)
            self.assertTrue(misc.intersection(container.items),fid)
            self.assertTrue(building.destroy_container(container)[0])
            state.ground_piles.clear()
            self.assertIsNone(building.materialize_natural_container_at(pos))
            self.assertFalse(state.ground_piles)

    def test_species_specific_misc_is_recovered_once_by_butchering(self):
        for row in misc_catalog():
            if row['source']!='animal':continue
            iid=row['item_id'];sid=row['species'][0]
            state=LivingWorldState();state.carcasses['body']=CarcassState('body',sid,0,0,0,0,100)
            inv=Inventory({'core:stone_knife':1})
            processing=ProcessingSystem(state,self.registry,None,b'animal-loot-test')
            self.assertTrue(processing.process_carcass('body','butcher',inv,5,0)[0],iid)
            self.assertGreater(inv.count(iid),0,iid)
            before=dict(inv.items)
            self.assertFalse(processing.process_carcass('body','butcher',inv,5,0)[0])
            self.assertEqual(inv.items,before)


if __name__=='__main__':
    unittest.main()
