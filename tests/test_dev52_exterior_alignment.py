"""Every new authored facade keeps its independently selectable real portal."""
import os
import unittest
from unittest.mock import patch

from worldseed.systems.building_shells import BuildingShell
from worldseed.systems.building_variants import catalog
from worldseed.systems.interior_state import InteriorPlan
from worldseed.systems.state import pos_key
from worldseed.ui.exterior_view import draw_shells, shell_at_pointer
from worldseed.ui.pygame_terminal import PygameTerminal


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class Dev52ExteriorAlignmentTests(unittest.TestCase):
    def test_all_thirty_pinned_thresholds_align_at_four_zooms_without_discovery_writes(self):
        with patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'}):
            term = PygameTerminal(1280, 832)
            term.enter()
            try:
                used = term.pg.Rect(150, 130, 1000, 600)
                footprint = tuple((x, y) for y in range(6) for x in range(6))
                known = {pos_key(x, y, 0) for x, y in footprint}
                for variant in catalog():
                    shell = BuildingShell('shell:' + variant['asset'], 'town', variant['function'],
                                          'core:house', footprint, (3, 5), 'door:stable',
                                          0, 'rectangle', (0, 0, 5, 5))
                    plan = InteriorPlan('interior:' + shell.uid, shell.uid, shell.door_uid,
                                        3, 5, 0, 12000, 12000, variant_id=variant['id'])
                    before = plan.to_dict()
                    for size in (16, 28, 40, 56):
                        with self.subTest(variant=variant['id'], size=size):
                            hits = []
                            draw_shells(term, (shell,), used, 0, 0, size, known, known,
                                        hit_regions=hits, interior_plans={plan.uid: plan})
                            doors = [row for row in hits if row['kind'] == 'door']
                            bodies = [row for row in hits if row['kind'] == 'body']
                            self.assertEqual(len(doors), 1)
                            self.assertEqual(len(bodies), 1)
                            door = doors[0]
                            self.assertEqual(door['role'], 'facade')
                            self.assertEqual(door['target'], (3, 5))
                            self.assertEqual(door['rect'].midbottom,
                                             (used.x + 3 * size + size // 2,
                                              used.y + 6 * size - max(1, size // 10)))
                            context = {'used': used, 'shell_hit_regions': hits}
                            self.assertEqual(shell_at_pointer(context, door['rect'].center), (shell, 'door'))
                    self.assertEqual(plan.to_dict(), before)
                self.assertEqual(known, {pos_key(x, y, 0) for x, y in footprint})
            finally:
                term.restore()
