"""Physicalized settlement viewport projections are immutable and revision-aware."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from worldseed.systems.physicalization import (
    PhysicalizedSettlementCell, SettlementPhysicalizationSystem,
)


class SettlementViewportCacheTests(unittest.TestCase):
    def fixture(self):
        p=SettlementPhysicalizationSystem.__new__(SettlementPhysicalizationSystem)
        p.revision=0
        p._viewport_cell_snapshot=None
        p._viewport_shell_snapshot=None
        p._indoor_fixture_uids=set()
        p._cells={
            (1,2):PhysicalizedSettlementCell(1,2,'village',ground_piece_id='core:footpath_piece'),
            (-34,-1):PhysicalizedSettlementCell(-34,-1,'village',fixture_piece_uid='fixture:1',fixture_piece_id='core:bench'),
            (100,100):PhysicalizedSettlementCell(100,100,'distant'),
        }
        p._shells={
            'b':SimpleNamespace(bounds=(200,200,204,205)),
            'a':SimpleNamespace(bounds=(0,0,5,6)),
        }
        return p

    def test_same_view_skips_cell_scan_and_preserves_order(self):
        p=self.fixture()
        original=p.cells_in_bounds(-40,-4,5,8)
        self.assertEqual([(q.x,q.y) for q in original],[(1,2),(-34,-1)])
        with patch.object(p,'_project_cell',side_effect=AssertionError('redundant reconstruction')):
            repeated=p.cells_in_bounds(-40,-4,5,8)
        self.assertIs(repeated,original)
        other=p.cells_in_bounds(0,0,5,8)
        self.assertEqual([(q.x,q.y) for q in other],[(1,2)])
        self.assertIsNot(other,original)

    def test_revision_and_interior_registration_invalidate_immediately(self):
        p=self.fixture()
        first=p.cells_in_bounds(-40,-4,5,8)
        p.register_interior(SimpleNamespace(function='residence',
              furniture=[SimpleNamespace(uid='fixture:1')]))
        second=p.cells_in_bounds(-40,-4,5,8)
        self.assertIsNot(first,second)
        self.assertEqual(second[1].fixture_piece_id,'')
        p._cells[(2,3)]=PhysicalizedSettlementCell(2,3,'new')
        p.revision+=1
        third=p.cells_in_bounds(-40,-4,5,8)
        self.assertEqual(len(third),3)
        p.clear()
        self.assertEqual(p.cells_in_bounds(-40,-4,5,8),())

    def test_shell_projection_reuses_exact_bounds_and_revision(self):
        p=self.fixture()
        nearby=p.shells_in_bounds(-5,-5,8,8)
        self.assertEqual(len(nearby),1)
        self.assertIs(p.shells_in_bounds(-5,-5,8,8),nearby)
        self.assertEqual(p.shells_in_bounds(200,200,206,207)[0],p._shells['b'])
        p.revision+=1
        after=p.shells_in_bounds(-5,-5,8,8)
        self.assertIsNot(after,nearby)
        self.assertEqual(after,nearby)


if __name__=='__main__':
    unittest.main()
