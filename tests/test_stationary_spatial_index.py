"""Maintained outdoor structure, pile and carcass indexes.

Rendering reads existing indexes and never walks whole distant populations.
"""
import unittest
from types import SimpleNamespace

from worldseed.core.coords import WorldPos
from worldseed.systems.building import BuildingSystem
from worldseed.systems.spatial_index import SpatialObjectMap
from worldseed.systems.state import (
    CarcassState, ContainerState, GroundPile, LivingWorldState,
    StructureInstance, pos_key,
)
from worldseed.ui.pygame_terminal import PygameTerminal


class NoGlobalScan(SpatialObjectMap):
    def values(self):
        raise AssertionError('rendering scanned a whole indexed collection')
    def items(self):
        raise AssertionError('rendering scanned a whole indexed collection')
    def __iter__(self):
        raise AssertionError('rendering iterated a whole indexed collection')


def structure(x, y=0, z=0):
    return StructureInstance('core:campfire', x, y, z)


def pile(x, y=0, z=0):
    return GroundPile(x, y, z, {'core:stone': 3})


def carcass(uid, x, y=0, z=0):
    return CarcassState(uid, 'core:deer', x, y, z, 12)


def renderer_view(state, left=0, top=0, right=5, bottom=5, z=0, terminal=None):
    terminal=terminal or PygameTerminal.__new__(PygameTerminal)
    if not hasattr(terminal, '_entity_spatial_cache_key'):
        terminal._entity_spatial_cache_key=None
        terminal._entity_spatial_cache=None
    sim=SimpleNamespace(state=state, clock=SimpleNamespace(minute=0), npcs=None)
    return terminal, terminal._spatial_state_views(sim,left,top,right,bottom,z)


class StationarySpatialIndexTests(unittest.TestCase):
    def test_negative_coordinates_layers_and_mapping_lifecycle(self):
        m=SpatialObjectMap()
        first=structure(-1,-1)
        m['-1,-1,0']=first
        underground=structure(-1,-1,-1)
        m['-1,-1,-1']=underground
        self.assertEqual(m.near_rect(-32,-32,-1,-1,0),(first,))
        self.assertEqual(m.near_rect(-32,-32,-1,-1,-1),(underground,))
        self.assertEqual(m.near_rect(0,0,-1,-1,0),())
        m['-1,-1,0']=structure(100,100)
        self.assertEqual(m.near_rect(-32,-32,-1,-1,0),())
        moved=m.pop('-1,-1,0')
        moved.x,moved.y=-33,-34
        m['-33,-34,0']=moved
        self.assertEqual(m.near_rect(-33,-34,-33,-34,0),(moved,))
        moved.x=65
        m.refresh_key('-33,-34,0')
        self.assertEqual(m.near_rect(-33,-34,-33,-34,0),())
        self.assertEqual(m.near_rect(65,-34,65,-34,0),(moved,))
        m.clear()
        self.assertEqual(m.near_rect(65,-34,65,-34,0),())

    def test_renderer_reads_only_indexed_nearby_objects_and_updates_immediately(self):
        near_structure=structure(2,3)
        near_pile=pile(-2,0)
        near_carcass=carcass('near',3,-1)
        structures=NoGlobalScan({'s':near_structure})
        piles=NoGlobalScan({'p':near_pile})
        carcasses=NoGlobalScan({'c':near_carcass})
        # All three populations grow distant, but a local read stays bucket-limited.
        for i in range(1600):
            structures['far:'+str(i)]=structure(10000+i,10000)
            piles['far:'+str(i)]=pile(10000+i,10000)
            carcasses['far:'+str(i)]=carcass('far:'+str(i),10000+i,10000)
        state=SimpleNamespace(
            structures=structures,ground_piles=piles,carcasses=carcasses,
            containers={},crops={},fires={},fluids={},animal_signs={},
            animal_homes={},npcs={},creatures={},
        )
        terminal,visible=renderer_view(state,-5,-5,5,5)
        self.assertEqual(visible['structures'],[near_structure])
        self.assertEqual(visible['ground_piles'],[near_pile])
        self.assertEqual(visible['carcasses'],[near_carcass])
        stationary_cache=terminal._entity_spatial_cache
        structures.pop('s')
        near_structure.x=96
        structures['moved']=near_structure
        piles.pop('p')
        carcasses['c']=carcass('replaced',120,120)
        _,after=renderer_view(state,-5,-5,5,5,terminal=terminal)
        self.assertEqual(after['structures'],[])
        self.assertEqual(after['ground_piles'],[])
        self.assertEqual(after['carcasses'],[])
        self.assertIs(terminal._entity_spatial_cache,stationary_cache)
        _,moved=renderer_view(state,96,0,96,5,terminal=terminal)
        self.assertEqual(moved['structures'],[near_structure])

    def test_renderer_preserves_historical_bucket_order(self):
        later_bucket=structure(64,0)
        earlier_bucket=structure(-1,0)
        # Insert opposite to viewport bucket traversal; drawing sorts by bucket.
        state=SimpleNamespace(
            structures=SpatialObjectMap({'later':later_bucket,'earlier':earlier_bucket}),
            ground_piles={},carcasses={},containers={},crops={},fires={},fluids={},
            animal_signs={},animal_homes={},npcs={},creatures={},
        )
        _,view=renderer_view(state,-1,0,64,1)
        self.assertEqual(view['structures'],[earlier_bucket,later_bucket])

    def test_attached_structure_follows_moved_container_and_keeps_goods(self):
        state=LivingWorldState()
        state.structures=SpatialObjectMap()
        state.containers=SpatialObjectMap()
        original=WorldPos(0,0,0)
        destination=WorldPos(65,-34,0)
        old_key=pos_key(0,0,0)
        new_key=pos_key(destination.x,destination.y,destination.z)
        held=ContainerState('storage:test',0,0,0,'player',5000,5000,
                            {'core:stone':7},movable=True)
        support=StructureInstance('core:chest',0,0,0)
        state.containers[old_key]=held
        state.structures[old_key]=support
        allowed,message=BuildingSystem(state,SimpleNamespace()).move_container(held,destination)
        self.assertTrue(allowed,message)
        self.assertIs(state.containers[new_key],held)
        self.assertIs(state.structures[new_key],support)
        self.assertEqual(held.items,{'core:stone':7})
        self.assertEqual(state.structures.near_rect(0,0,0,0,0),())
        self.assertEqual(state.structures.near_rect(65,-34,65,-34,0),(support,))

    def test_save_roundtrip_does_not_include_derived_indexes(self):
        state=LivingWorldState()
        state.structures=SpatialObjectMap({'-2,1,0':structure(-2,1)})
        state.ground_piles=SpatialObjectMap({'3,4,0':pile(3,4)})
        state.carcasses=SpatialObjectMap({'dead':carcass('dead',5,6)})
        saved=state.to_dict()
        self.assertEqual(set(saved['structures']),{'-2,1,0'})
        self.assertEqual(set(saved['ground_piles']),{'3,4,0'})
        self.assertEqual(set(saved['carcasses']),{'dead'})
        self.assertNotIn('_buckets',str(saved))
        loaded=LivingWorldState.from_dict(saved)
        self.assertIs(type(loaded.structures),dict)
        self.assertIs(type(loaded.ground_piles),dict)
        self.assertIs(type(loaded.carcasses),dict)
        self.assertEqual(loaded.ground_piles['3,4,0'].items,{'core:stone':3})


if __name__=='__main__':
    unittest.main()
