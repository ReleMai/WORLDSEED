"""Bounded per-viewport resource projection without stale LOS observations."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

from worldseed.ui.pygame_terminal import PygameTerminal


class ResourceViewFastpathTests(unittest.TestCase):
    def fixture(self):
        ui=PygameTerminal.__new__(PygameTerminal)
        ui._resource_cell_cache={}
        ui._resource_view_snapshot=None
        ui._resource_visual=lambda *args: ('tree',args)
        resource=SimpleNamespace(feature_id='core:fallen_branch',stage='ready')
        feature=Mock(return_value=resource)
        res=SimpleNamespace(revision=0,feature_at=feature)
        state=SimpleNamespace(structures={},containers={},crops={},soils={})
        sim=SimpleNamespace(state=state,resources=res,clock=SimpleNamespace(minute=720))
        return ui,sim,feature

    def test_exact_unchanged_view_avoids_each_cell_and_reuses_response(self):
        ui,sim,feature=self.fixture()
        visible={'0,0,0','1,0,0'}
        first=ui._resource_view(sim,visible,0,0,0,3,3)
        self.assertEqual(len(first),2)
        self.assertEqual(feature.call_count,2)
        with patch('worldseed.ui.pygame_terminal.pos_key',
                   side_effect=AssertionError('unnecessary whole-viewport scan')):
            again=ui._resource_view(sim,visible,0,0,0,3,3)
        self.assertIs(first,again)
        feature.assert_called()

        # Same-count LOS replacement invalidates the viewport snapshot.
        visible={'0,0,0','2,0,0'}
        third=ui._resource_view(sim,visible,0,0,0,3,3)
        self.assertIsNot(third,first)
        self.assertEqual(set(third),{(0,0,0),(2,0,0)})
        self.assertEqual(feature.call_count,3)

    def test_authoritative_resource_mutation_and_day_invalidate(self):
        ui,sim,feature=self.fixture()
        visible={'0,0,0'}
        first=ui._resource_view(sim,visible,0,-1,-1,4,4)
        sim.resources.revision += 1
        second=ui._resource_view(sim,visible,0,-1,-1,4,4)
        self.assertIsNot(first,second)
        self.assertEqual(feature.call_count,2)
        sim.clock.minute+=1440
        third=ui._resource_view(sim,visible,0,-1,-1,4,4)
        self.assertIsNot(second,third)
        self.assertEqual(feature.call_count,3)
        fourth=ui._resource_view(sim,visible,0,0,-1,4,4)
        self.assertIsNot(fourth,third)

    def test_new_simulation_identity_does_not_reuse_old_world_projection(self):
        ui,sim,feature=self.fixture()
        first=ui._resource_view(sim,{'0,0,0'},0,0,0,2,2)
        sim2=SimpleNamespace(state=sim.state,resources=sim.resources,clock=sim.clock)
        again=ui._resource_view(sim2,{'0,0,0'},0,0,0,2,2)
        self.assertIsNot(first,again)


if __name__=='__main__':
    unittest.main()
