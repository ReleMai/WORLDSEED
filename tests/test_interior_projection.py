import unittest
from types import SimpleNamespace

from worldseed.core.coords import WorldPos
from worldseed.systems.interior_state import InteriorFurniture, InteriorPlan
from worldseed.systems.physicalization import PhysicalizedSettlementCell, SettlementPhysicalizationSystem


class InteriorProjectionTests(unittest.TestCase):
    def fixture(self):
        pieces={
            "core:bed_piece":SimpleNamespace(passable=False,blocks_sight=False,glyph="B",name="Bed"),
            "core:floor_piece":SimpleNamespace(passable=True,blocks_sight=False,glyph=".",name="Floor"),
            "core:wall_piece":SimpleNamespace(passable=False,blocks_sight=True,glyph="#",name="Wall"),
        }
        physical=SettlementPhysicalizationSystem(None,SimpleNamespace(settlement_pieces=pieces),None,None)
        cell=PhysicalizedSettlementCell(3,4,"settlement:test",structure_id="home:test",room_id="room:test",
            ground_piece_id="core:floor_piece",fixture_piece_id="core:bed_piece",fixture_piece_uid="fixture:bed",roof_piece_id="core:roof_piece")
        physical._cells[(3,4)]=cell
        room=SimpleNamespace(uid="room:test",kind="bedroom",enclosed=True,sheltered=True,roof_percent=100,area=12,doorway_cells=[(3,5)],structure_plan_id="home:test")
        physical._rooms[room.uid]=room
        plan=InteriorPlan("interior:home:test","home:test","door:test",3,5,0,10000,10000,
            furniture=[InteriorFurniture("fixture:bed","core:bed_piece",425,625,950,1450)])
        return physical,cell,plan

    def test_prepared_home_fixture_moves_out_of_outdoor_projection(self):
        physical,original,plan=self.fixture()
        pos=WorldPos(3,4)
        self.assertFalse(physical.passable(pos))
        revision=physical.revision
        physical.register_interior(plan)
        projected=physical.cell_at(pos)
        self.assertEqual(projected.fixture_piece_id,"")
        self.assertEqual(projected.ground_piece_id,original.ground_piece_id)
        self.assertEqual(projected.roof_piece_id,original.roof_piece_id)
        self.assertEqual(projected.structure_id,"home:test")
        self.assertTrue(physical.passable(pos))
        self.assertEqual(physical.glyph_at(pos),".")
        self.assertEqual(physical.cells(),(projected,))
        self.assertEqual(physical.cells_in_bounds(0,0,10,10),(projected,))
        self.assertGreater(physical.revision,revision)
        self.assertEqual(physical._cells[(3,4)],original)
        self.assertEqual(plan.furniture[0].uid,"fixture:bed")
        report=physical.room_at(pos)
        self.assertEqual(report["beds"],1)
        self.assertFalse(report["stations"])

    def test_fixture_projection_preserves_wall_collision(self):
        physical,cell,plan=self.fixture()
        physical._cells[(3,4)]=physical._merge_cell(cell,x=3,y=4,settlement_id=cell.settlement_id,
            structure_piece_id="core:wall_piece",structure_piece_uid="wall:test",structure_piece_role="wall")
        physical.register_interior(plan)
        self.assertFalse(physical.passable(WorldPos(3,4)))
        self.assertTrue(physical.blocks_sight(WorldPos(3,4)))

    def test_load_attachment_reconstructs_mask_without_mutating_plan(self):
        physical,_,plan=self.fixture()
        before=plan.to_dict()
        state=SimpleNamespace(interiors={plan.uid:plan})
        physical.attach_interior_state(state)
        revision=physical.revision
        physical.register_interior(plan)
        self.assertEqual(physical.revision,revision)
        self.assertFalse(physical.cell_at(WorldPos(3,4)).fixture_piece_id)
        self.assertEqual(plan.to_dict(),before)

    def test_workshop_projection_waits_for_activity_space_migration(self):
        physical,_,plan=self.fixture()
        plan.function="workshop"
        physical.register_interior(plan)
        self.assertEqual(physical.cell_at(WorldPos(3,4)).fixture_piece_id,"core:bed_piece")


if __name__=="__main__":
    unittest.main()
