"""Container indexes remain bounded and preserve storage identities and goods."""
import unittest
from types import SimpleNamespace
from worldseed.systems.spatial_index import SpatialObjectMap
from worldseed.ui.pygame_terminal import PygameTerminal


def container(uid, x, y=0, z=0, interior=''):
    return SimpleNamespace(uid=uid, x=x, y=y, z=z,
                           interior_space_id=interior, items={'core:stone':3})


class NoWholeScan(SpatialObjectMap):
    def items(self):
        raise AssertionError('renderer enumerated all containers')
    def values(self):
        raise AssertionError('renderer enumerated all containers')


class ContainerSpatialIndexTests(unittest.TestCase):
    def test_negative_bounds_replacement_and_relocation(self):
        a=container('a',-1,-1)
        m=SpatialObjectMap({'-1,-1,0':a})
        self.assertEqual(m.near_rect(-32,-32,-1,-1,0),(a,))
        m['-1,-1,0']=container('b',300,300)
        self.assertEqual(m.near_rect(-32,-32,-1,-1,0),())
        moved=m.pop('-1,-1,0')
        moved.x,moved.y=64,64
        m['64,64,0']=moved
        self.assertEqual(m.near_rect(64,64,64,64,0),(moved,))
        moved.x,moved.y=97,97
        m.refresh_key('64,64,0')
        self.assertEqual(m.near_rect(64,64,64,64,0),())
        self.assertEqual(m.near_rect(97,97,97,97,0),(moved,))
        self.assertEqual(moved.items,{'core:stone':3})

    def test_bounded_renderer_query_with_distant_containers(self):
        m=NoWholeScan()
        near=container('near',1,2)
        m['1,2,0']=near
        m['interior']=container('hidden',1,2,0,'interior:one')
        for n in range(1500):
            m[str(n)]=container(str(n),10000+n,20000)
        state=SimpleNamespace(containers=m,structures={},crops={},fires={},
                              fluids={},ground_piles={},carcasses={},animal_signs={},
                              animal_homes={},creatures={},npcs={})
        sim=SimpleNamespace(state=state,npcs=None,clock=SimpleNamespace(minute=0))
        term=PygameTerminal.__new__(PygameTerminal)
        term._entity_spatial_cache_key=None
        term._entity_spatial_cache=None
        got=term._spatial_state_views(sim,0,0,5,5,0)
        self.assertEqual(got['containers'],[near])
        cache=term._entity_spatial_cache
        moving=m.pop('1,2,0')
        moving.x=70
        m['70,2,0']=moving
        self.assertEqual(term._spatial_state_views(sim,0,0,5,5,0)['containers'],[])
        self.assertIs(cache,term._entity_spatial_cache)
        self.assertEqual(term._spatial_state_views(sim,70,0,71,5,0)['containers'],[near])


if __name__=='__main__':
    unittest.main()
