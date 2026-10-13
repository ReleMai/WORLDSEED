"""NPC presentation reads the maintained locator without world-population scans."""
import unittest

from worldseed.systems.ai import NPCSystem
from worldseed.systems.history import HistorySystem
from worldseed.systems.state import LivingWorldState, NPCState
from worldseed.ui.pygame_terminal import PygameTerminal
from types import SimpleNamespace


class NoPopulationScan(dict):
    def values(self):
        raise AssertionError('presentation scanned the whole NPC population')
    def items(self):
        raise AssertionError('presentation scanned the whole NPC population')
    def __iter__(self):
        raise AssertionError('presentation scanned the whole NPC population')


def actor(uid, x, y=0):
    return NPCState(uid, uid, 30, 'farmer', [], x, y, 0, 'town', 'faction')


class NPCPresentationIndexTests(unittest.TestCase):
    def setUp(self):
        self.state=LivingWorldState()
        # Deliberately insert opposite to UID order. Drawing keeps the old
        # order within each 32-cell presentation bucket.
        for npc in (actor('z:first', 5), actor('a:second', 6),
                    actor('negative', -3), actor('far', 10000)):
            self.state.npcs[npc.uid]=npc
        self.ai=NPCSystem(self.state,b'presentation-index',HistorySystem(self.state))
        self.sim=SimpleNamespace(state=self.state,npcs=self.ai,clock=SimpleNamespace(minute=720))
        self.term=PygameTerminal.__new__(PygameTerminal)
        self.term._entity_spatial_cache_key=None
        self.term._entity_spatial_cache=None
        self.state.npcs=NoPopulationScan(self.state.npcs)

    def view(self,left=0,right=10):
        return self.term._spatial_state_views(self.sim,left,0,right,10,0)

    def test_bounded_read_preserves_bucket_and_insertion_order(self):
        rows=self.term._spatial_state_views(self.sim,-5,0,10,10,0)['npcs']
        self.assertEqual([n.uid for n in rows],['negative','z:first','a:second'])

    def test_bucket_crossing_is_current_without_clock_count_or_static_rebuild(self):
        first=self.view()
        cache=self.term._entity_spatial_cache
        npc=self.state.npcs['far'];npc.x=7;self.ai._index_npc(npc)
        second=self.view()
        self.assertIs(cache,self.term._entity_spatial_cache)
        self.assertNotIn(npc,first['npcs'])
        self.assertIn(npc,second['npcs'])
        npc.x=96;self.ai._index_npc(npc)
        self.assertNotIn(npc,self.view()['npcs'])

    def test_death_removal_and_same_count_replacement_filter_stale_references(self):
        self.view()
        original=self.state.npcs['z:first'];original.alive=False
        self.assertNotIn(original,self.view()['npcs'])
        self.state.npcs.pop('a:second')
        replacement=actor('replacement',8)
        self.state.npcs[replacement.uid]=replacement;self.ai._index_npc(replacement)
        self.assertEqual([n.uid for n in self.view()['npcs']],['replacement'])

    def test_queries_are_observational_and_negative_bounds_keep_bucket_extent(self):
        positions=[(n.uid,n.x,n.y,n.z) for n in dict.values(self.state.npcs)]
        buckets={key:tuple(rows) for key,rows in self.ai._npc_spatial_buckets.items()}
        self.assertEqual([n.uid for n in self.view(-1,-1)['npcs']],['negative'])
        self.assertEqual(positions,[(n.uid,n.x,n.y,n.z) for n in dict.values(self.state.npcs)])
        self.assertEqual(buckets,{key:tuple(rows) for key,rows in self.ai._npc_spatial_buckets.items()})


if __name__=='__main__':
    unittest.main()
