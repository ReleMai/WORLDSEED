"""Remaining static spatial maps: bounded rendering, gameplay mutations and saves."""
import unittest
from types import SimpleNamespace

from worldseed.core.coords import WorldPos
from worldseed.systems.hunting import HuntingSystem
from worldseed.systems.spatial_index import SpatialObjectMap
from worldseed.systems.state import (
    AnimalHomeState, AnimalSignState, CropPlot, FireCell, FluidCell,
    LivingWorldState,
)
from worldseed.ui.pygame_terminal import PygameTerminal


class NoGlobalScan(SpatialObjectMap):
    def values(self):
        raise AssertionError('viewport or local action enumerated the world')
    def items(self):
        raise AssertionError('viewport or local action enumerated the world')


def sample(name,x,y=0,z=0,uid='local'):
    if name=='crops':
        return CropPlot('core:barley',x,y,z,60)
    if name=='fires':
        return FireCell(x,y,z,35,100)
    if name=='fluids':
        return FluidCell(x,y,z,'water',80)
    if name=='animal_signs':
        return AnimalSignState(uid,'core:deer',x,y,z,'track',60)
    if name=='animal_homes':
        return AnimalHomeState(uid,'core:deer',x,y,z,'den',60)
    raise ValueError(name)


NAMES=('crops','fires','fluids','animal_signs','animal_homes')


def context(mappings):
    state=SimpleNamespace(
        structures={},containers={},ground_piles={},carcasses={},
        crops=mappings.get('crops',{}),fires=mappings.get('fires',{}),
        fluids=mappings.get('fluids',{}),
        animal_signs=mappings.get('animal_signs',{}),
        animal_homes=mappings.get('animal_homes',{}),npcs={},creatures={},
    )
    sim=SimpleNamespace(state=state,npcs=None,clock=SimpleNamespace(minute=300))
    term=PygameTerminal.__new__(PygameTerminal)
    term._entity_spatial_cache_key=None
    term._entity_spatial_cache=None
    return sim,term


class RemainingSpatialIndexTests(unittest.TestCase):
    def test_all_five_types_bounded_rendering_without_hour_or_count_rebuild(self):
        maps={}
        near={}
        for name in NAMES:
            local=sample(name,-2,3,0,name+':near')
            far=sample(name,10000,10000,0,name+':far')
            mp=NoGlobalScan({'local':local,'far':far})
            for i in range(400):
                mp[str(i)]=sample(name,20000+i,19000,0,name+str(i))
            maps[name]=mp
            near[name]=local
        sim,term=context(maps)
        got=term._spatial_state_views(sim,-3,0,4,5,0)
        for name in NAMES:
            self.assertEqual(got[name],[near[name]])
        # Same-count replacement and removal take effect immediately, even if
        # the game clock never ticks or the renderer cache remains unchanged.
        for name in NAMES:
            obj=maps[name].pop('local')
            obj.x,obj.y=65,33
            maps[name]['relocated']=obj
        self.assertEqual(sum(len(term._spatial_state_views(sim,-3,0,4,5,0)[n]) for n in NAMES),0)
        moved=term._spatial_state_views(sim,65,33,65,33,0)
        for name in NAMES:
            self.assertEqual(moved[name],[near[name]])

    def test_negative_z_bucket_boundaries_and_refresh(self):
        for name in NAMES:
            mp=SpatialObjectMap()
            below=sample(name,-33,-32,-1,name)
            mp['a']=below
            self.assertEqual(mp.near_rect(-33,-32,-33,-32,-1),(below,))
            self.assertEqual(mp.near_rect(-33,-32,-33,-32,0),())
            below.x,below.y,below.z=-1,-1,0
            mp.refresh_key('a')
            self.assertEqual(mp.near_rect(-33,-32,-33,-32,-1),())
            self.assertEqual(mp.near_rect(-1,-1,-1,-1,0),(below,))

    def test_nearby_signs_homes_and_deduplication_do_not_scan(self):
        signs=NoGlobalScan({'near':sample('animal_signs',0,0,0,'near'),
                            'far':sample('animal_signs',200,200,0,'far')})
        homes=NoGlobalScan({'near':sample('animal_homes',1,0,0,'near'),
                            'far':sample('animal_homes',200,200,0,'far')})
        hunting=HuntingSystem.__new__(HuntingSystem)
        hunting.state=SimpleNamespace(animal_signs=signs,animal_homes=homes)
        pos=WorldPos(0,0,0)
        self.assertEqual([s.uid for s in hunting.nearby_signs(pos)],['near'])
        self.assertEqual([s.uid for s in hunting.signs_at(pos)],['near'])
        self.assertEqual([h.uid for h in hunting.nearby_homes(pos)],['near'])
        self.assertEqual(hunting.home_at(WorldPos(1,0,0)).uid,'near')
        hunter=SimpleNamespace(uid='near',species_id='core:deer')
        # Existing sign has different uid but identical source/time/type/place.
        existing=signs['near'];existing.source_uid=hunter.uid
        before=len(signs)
        hunting._write_sign(hunter,'track',pos,pos,60,50,'repeat')
        self.assertEqual(len(signs),before)

    def test_save_schema_unchanged_after_runtime_index(self):
        state=LivingWorldState()
        for name in NAMES:
            setattr(state,name,SpatialObjectMap({name:sample(name,-1,1,0,name)}))
        saved=state.to_dict()
        for name in NAMES:
            self.assertIn(name,saved)
            self.assertEqual(set(saved[name]),{name})
        self.assertNotIn('_positions',str(saved))
        restored=LivingWorldState.from_dict(saved)
        for name in NAMES:
            self.assertIs(type(getattr(restored,name)),dict)


if __name__=='__main__':
    unittest.main()
