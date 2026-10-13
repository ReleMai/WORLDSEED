"""Transient creature index: no renderer-side scans or second creature state."""
import unittest
from types import SimpleNamespace
from worldseed.systems.spatial_index import CreatureSpatialMap
from worldseed.systems.state import CreatureState, LivingWorldState
from worldseed.ui.pygame_terminal import PygameTerminal


def creature(uid,x,y=0,z=0):
    return CreatureState(uid,"core:deer",x,y,z,20)


class NoWholePopulationScan(CreatureSpatialMap):
    def items(self):
        raise AssertionError("local query enumerated global creatures")

    def values(self):
        raise AssertionError("local query enumerated global creatures")

    def __iter__(self):
        raise AssertionError("local query enumerated global creatures")


class CreatureSpatialIndexTests(unittest.TestCase):
    def test_negative_boundaries_insertion_and_levels(self):
        mapping=CreatureSpatialMap()
        for c in (creature("first",-1,-1),creature("second",0,0),
                  creature("third",16,16),creature("underground",-1,-1,-1)):
            mapping[c.uid]=c
        self.assertEqual([c.uid for c in mapping.near_rect(-16,-16,0,0,0)],
                         ["first","second"])
        self.assertEqual([c.uid for c in mapping.near_rect(-1,-1,-1,-1,-1)],
                         ["underground"])
        self.assertEqual(mapping.near_rect(0,0,-1,0,0),())

    def test_move_crosses_bucket_and_same_count_replacement(self):
        a=creature("a",15,15);b=creature("b",256,256)
        mapping=CreatureSpatialMap({"a":a,"b":b})
        a.x,a.y=16,16
        mapping.refresh(a)
        self.assertEqual(mapping.near_rect(15,15,15,15,0),())
        self.assertEqual(mapping.near_rect(16,16,16,16,0),(a,))
        mapping["b"]=creature("b",-20,-20)
        self.assertEqual(len(mapping),2)
        self.assertEqual(mapping.near_rect(256,256,256,256,0),())
        self.assertEqual([c.uid for c in mapping.near_rect(-20,-20,-20,-20,0)],["b"])
        mapping.pop("a")
        self.assertEqual(mapping.near_rect(16,16,16,16,0),())

    def test_population_reads_are_bounded_without_mapping_iteration(self):
        mapping=NoWholePopulationScan()
        mapping["near"]=creature("near",2,3)
        for i in range(1200):
            mapping["far:"+str(i)]=creature("far:"+str(i),10000+i,10000)
        self.assertEqual([c.uid for c in mapping.near_rect(-32,-32,32,32,0)],["near"])
        self.assertEqual(mapping.order_of("near"),0)
        mapping.clear()
        self.assertEqual(mapping.near_rect(-32,-32,32,32,0),())

    def test_renderer_reads_index_and_never_rebuilds_static_cache_for_motion(self):
        state=LivingWorldState()
        state.creatures=NoWholePopulationScan({"near":creature("near",15,1)})
        sim=SimpleNamespace(state=state,clock=SimpleNamespace(minute=100),npcs=None)
        renderer=PygameTerminal.__new__(PygameTerminal)
        renderer._entity_spatial_cache_key=None
        renderer._entity_spatial_cache=None
        first=renderer._spatial_state_views(sim,0,0,2,2,0)
        self.assertEqual([c.uid for c in first["creatures"]],["near"])
        previous=renderer._entity_spatial_cache
        state.creatures["near"].x=64
        state.creatures.refresh(state.creatures["near"])
        next_view=renderer._spatial_state_views(sim,0,0,2,2,0)
        self.assertEqual(next_view["creatures"],[])
        self.assertIs(previous,renderer._entity_spatial_cache)
        self.assertEqual([c.uid for c in renderer._spatial_state_views(sim,64,0,65,2,0)["creatures"]],["near"])

    def test_dict_lifecycle_and_serialization_does_not_persist_buckets(self):
        state=LivingWorldState()
        state.creatures=CreatureSpatialMap({"a":creature("a",-32,4)})
        payload=state.to_dict()
        self.assertIn("a",payload["creatures"])
        self.assertNotIn("_positions",str(payload))
        loaded=LivingWorldState.from_dict(payload)
        self.assertIs(type(loaded.creatures),dict)
        mapped=CreatureSpatialMap(loaded.creatures)
        self.assertEqual(mapped.near_rect(-32,4,-32,4,0),(loaded.creatures["a"],))
        uid,c=mapped.popitem()
        self.assertEqual(uid,"a")
        self.assertEqual(mapped.near_rect(-32,4,-32,4,0),())


if __name__=="__main__":
    unittest.main()
