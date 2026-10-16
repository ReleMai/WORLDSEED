"""Live GPU props reuse authority, prepared indexes and exact current sight."""
from contextlib import ExitStack, contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from tools.reference_scene_fixtures import build_fixture
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.presentation.gpu_objects import (
    MAX_PREPARED_OBJECTS, PreparedObject, capture_objects, capture_roofs,
    object_instances, object_source, resource_source,
)
from worldseed.presentation.visuals import VisualRegistry
from worldseed.presentation.worldspace import (
    SceneVisibility, VisualLayer, WorldCamera, WorldFoot, project_scene,
)
from worldseed.systems.physicalization import PhysicalizedSettlementCell
from worldseed.systems.state import (
    AnimalHomeState, AnimalSignState, CarcassState, ContainerState, CropPlot,
    GroundPile, RoofState, StructureInstance, pos_key,
)


def forbidden(*args, **kwargs):
    raise AssertionError('live prop projection must not prepare or scan world state')


class AssetSource:
    def __init__(self):
        self._visuals = VisualRegistry.load_default()

    def asset(self, path):
        self.last = path
        return ('asset:'+str(path), 1, b'\x55\x99\x44\xff'*4, 2, 2)


class GpuObjectContracts(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    @contextmanager
    def fixture(self):
        with TemporaryDirectory() as directory:
            fixture = build_fixture('forest', self.registry, Path(directory),
                                    width=640, height=480, zoom=28)
            try:
                yield fixture
            finally:
                fixture.close()

    def camera(self, sim):
        p = sim.player_pos
        return WorldCamera(WorldFoot(p.x+.5, p.y+.5, p.z), 640, 480, 28)

    def seed_props(self, sim):
        sim.state.structures[pos_key(256,256,0)] = StructureInstance('core:workbench',256,256,0)
        sim.state.ground_piles[pos_key(257,256,0)] = GroundPile(257,256,0,{'core:wood':3})
        sim.state.crops[pos_key(257,256,0)] = CropPlot('core:wheat',257,256,0,0,growth=80,mature=True)
        sim.state.containers[pos_key(256,257,0)] = ContainerState('stash',256,257,0,'secret owner',1000,1000,
            items={'core:gold':999},source_id='core:storage_basket')
        sim.state.carcasses['dead'] = CarcassState('dead','core:deer',257,257,0,0)

    def test_real_fixture_capture_projection_are_observational_and_detached(self):
        with self.fixture() as fixture:
            sim = fixture.sim
            self.seed_props(sim)
            cells = frozenset((x,y,0) for x in (256,257) for y in (256,257))
            before = fixture.authority_fingerprint()
            queries = []
            fixture.db.connection.set_trace_callback(queries.append)
            try:
                with ExitStack() as guards:
                    for owner, method in ((sim.world,'tile_at'),(sim.world,'prepared_tile_at'),
                            (sim.resources,'feature_at'),(sim,'_discover'),
                            (sim.settlement_physicalization,'cells_in_bounds'),
                            (sim.settlement_physicalization,'shells_in_bounds')):
                        guards.enter_context(patch.object(owner,method,forbidden))
                    rows = capture_objects(sim,cells,self.camera(sim))
                    instances = object_instances(rows)
                    projection = project_scene(instances,self.camera(sim),SceneVisibility(cells))
            finally:
                fixture.db.connection.set_trace_callback(None)
            self.assertEqual(queries,[])
            self.assertEqual(before,fixture.authority_fingerprint())
            self.assertEqual({r.kind for r in rows},{'structure','pile','crop','container','carcass'})
            self.assertEqual(len(projection.visuals),len(rows))
            self.assertTrue(all(not instance.physical_cells for instance in instances))
            self.assertFalse(any(hasattr(row,'items') or hasattr(row,'owner') for row in rows))
            with self.assertRaises(FrozenInstanceError):
                rows[0].content_id = 'core:forge'
            sim.state.structures[pos_key(256,256,0)].structure_id = 'core:forge'
            sim.state.ground_piles[pos_key(257,256,0)].items.clear()
            self.assertIn('core:workbench',{row.content_id for row in rows})
            self.assertIn('core:wood',{row.content_id for row in rows})

    def test_exact_current_cells_exclude_memory_offscreen_and_interior_storage(self):
        with self.fixture() as fixture:
            sim = fixture.sim
            self.seed_props(sim)
            sim.state.containers[pos_key(256,257,0)].interior_space_id='private-bedroom'
            rows=capture_objects(sim,frozenset({(256,256,0),(256,257,0),(9999,9999,0)}),self.camera(sim))
            self.assertEqual([(r.kind,r.content_id) for r in rows],[('structure','core:workbench')])
            self.assertEqual(capture_objects(sim,frozenset(),self.camera(sim)),())

    def test_roof_capture_never_copies_covered_props_or_hidden_roofs(self):
        with self.fixture() as fixture:
            sim=fixture.sim
            self.seed_props(sim)
            sim.state.roofs[pos_key(256,256,0)]=RoofState('core:wood_roof',256,256,0)
            sim.state.roofs[pos_key(257,256,0)]=RoofState('core:stone_roof',257,256,0)
            sim.state.roofs[pos_key(256,257,0)]=RoofState('core:wood_roof',256,257,0,condition=0)
            cells=frozenset({(256,256,0),(256,257,0)})
            before=fixture.authority_fingerprint()
            roofs=capture_roofs(sim,self.camera(sim),cells)
            self.assertEqual(len(roofs),1)
            self.assertEqual(roofs[0].content_id,'core:wood_roof')
            self.assertIs(roofs[0].layer,VisualLayer.OVERHEAD)
            self.assertEqual([r.kind for r in capture_objects(sim,{(256,256,0)},self.camera(sim))],['roof'])
            self.assertEqual(before,fixture.authority_fingerprint())

    def test_local_spatial_maps_are_required_never_fallback_global_values(self):
        with self.fixture() as fixture:
            sim=fixture.sim
            self.seed_props(sim)
            real=sim.state.carcasses
            class NoScan(dict):
                __iter__=values=items=forbidden
            sim.state.carcasses=NoScan(real)
            try:
                rows=capture_objects(sim,{(257,257,0)},self.camera(sim))
                self.assertEqual(rows,())
            finally:
                sim.state.carcasses=real

    def test_private_plan_omits_floor_fixtures_and_wildlife(self):
        with self.fixture() as fixture:
            sim=fixture.sim
            self.seed_props(sim)
            sim.state.carcasses['private']=CarcassState('private','core:deer',256,256,0,0)
            physical=PhysicalizedSettlementCell(256,256,'settlement',room_id='private-room',
                ground_piece_id='core:plank_floor_piece',fixture_piece_id='core:bed_piece',
                roof_piece_id='core:thatch_roof_piece')
            with patch.object(sim.settlement_physicalization,'cell_at',return_value=physical):
                self.assertEqual(capture_objects(sim,{(256,256,0)},self.camera(sim)),())

    def test_hunting_signs_homes_preserve_existing_discovery_skill_gate(self):
        with self.fixture() as fixture:
            sim=fixture.sim
            for uid,kind,strength in [('hidden','track',50),('seen','blood',70)]:
                sim.state.animal_signs[uid]=AnimalSignState(uid,'core:deer',256,256,0,kind,0,strength=strength)
            for uid,discovered in [('hidden-home',False),('seen-home',True)]:
                sim.state.animal_homes[uid]=AnimalHomeState(uid,'core:deer',256,256,0,'den',0,discovered=discovered)
            with patch.object(sim,'player_skill',return_value=0):
                rows=capture_objects(sim,{(256,256,0)},self.camera(sim))
            self.assertEqual({r.uid for r in rows},{'sign:seen','home:seen-home'})
            with patch.object(sim,'player_skill',return_value=1):
                rows=capture_objects(sim,{(256,256,0)},self.camera(sim))
            self.assertIn('sign:hidden',{r.uid for r in rows})

    def test_prepared_roads_fences_use_original_piece_ids_and_art(self):
        with self.fixture() as fixture:
            sim=fixture.sim
            candidates=list(self.registry.settlement_pieces.values())
            road=next(p for p in candidates if p.category=='road')
            fence=next(p for p in candidates if 'fence' in p.tags)
            cell=PhysicalizedSettlementCell(256,256,'town',ground_piece_id=road.id,
                                           structure_piece_id=fence.id,structure_piece_role='yard')
            with patch.object(sim.settlement_physicalization,'cell_at',return_value=cell):
                rows=capture_objects(sim,{(256,256,0)},self.camera(sim))
            self.assertEqual({r.content_id for r in rows},{road.id,fence.id})
            self.assertIs(next(r for r in rows if r.content_id==road.id).layer,VisualLayer.LOW_DETAIL)
            source=AssetSource()
            for row in rows:
                self.assertTrue(object_source(source,row))
                self.assertTrue(source.last.is_file())

    def test_all_non_tree_resources_resolve_existing_art_and_budget_validation(self):
        source=AssetSource()
        for content_id,definition in self.registry.resources.items():
            if content_id in {'core:oak_tree','core:pine_tree'}:
                continue
            row=PreparedObject('resource','resource',content_id,WorldFoot(256.5,256.95,0))
            self.assertTrue(resource_source(source,row.instance()),content_id)
            self.assertTrue(source.last.is_file(),content_id)
        with self.assertRaises(ValueError):
            PreparedObject('bad','structure','core:bed',WorldFoot(.5,.9,0),width=float('nan'))
        row=PreparedObject('ok','structure','core:bed',WorldFoot(.5,.9,0))
        with self.assertRaises(ValueError):
            object_instances((row,)*(MAX_PREPARED_OBJECTS+1))

    def test_real_atlas_and_yard_sources_are_small_cached_static_textures(self):
        try:
            import pygame as pg
        except ImportError:
            self.skipTest('optional pygame source-art checks')
        from worldseed.presentation.gpu_scene_bridge import GpuMaterialSource
        materials=GpuMaterialSource(pg)
        instance=PreparedObject('log','resource','core:hollow_log_cache',WorldFoot(256.5,256.95,0)).instance()
        first=resource_source(materials,instance)
        self.assertEqual(first,resource_source(materials,instance))
        self.assertEqual(first[-2:],(128,128))
        self.assertEqual(len(first[2]),128*128*4)
        fence=next(p for p in self.registry.settlement_pieces.values() if {'fence','yard'}<=set(p.tags))
        row=PreparedObject('fence','settlement_piece',fence.id,WorldFoot(256.5,256.95,0),
                           category=fence.category,material=fence.material,tags=fence.tags)
        texture=object_source(materials,row)
        self.assertEqual(texture[-2:],(96,96))
        self.assertTrue(any(texture[2][3::4]))
        self.assertEqual(texture,object_source(materials,row))
