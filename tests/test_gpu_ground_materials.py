"""Natural ground reads detached admitted neighbors and bounded cached art."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from worldseed.presentation.gpu_ground import ground_material, natural_ground
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry


class Materials:
    def __init__(self):self.cache={};self.loads=0
    def _read(self,key,loader):
        if key not in self.cache:self.cache[key]=loader()
        return self.cache[key]
    def asset(self,path):
        def load():
            self.loads+=1
            value=(sum(str(path).encode())%100)+100
            return (str(path),1,bytes((value,value,value,255))*4,2,2)
        return self._read(('file',str(path)),load)


class ContinuousGroundContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.definitions=ContentRegistry.load(DATA_DIR).terrains

    def test_current_cannot_read_unseen_or_remembered_neighbor_material(self):
        class Guarded(dict):
            def get(self,key,default=None):
                if key not in admitted:raise AssertionError('unadmitted material lookup')
                return super().get(key,default)
        cell=(0,0,0);admitted=frozenset({cell,(1,0,0)})
        terrain=Guarded({cell:'core:grass',(1,0,0):'core:forest',(-1,0,0):'core:rock'})
        materials=Materials()
        source,blend=ground_material(materials,cell,'core:grass',terrain,admitted,self.definitions)
        self.assertEqual(blend.widths,(0.,.42,0.,0.))
        self.assertEqual(blend.neighbors[0].texture_id,source[0])
        self.assertNotEqual(blend.neighbors[1].texture_id,source[0])
        self.assertEqual(len(blend.neighbors),8)

    def test_same_ground_uses_shared_canonical_source_without_cell_variant_seams(self):
        materials=Materials();terrain={(x,y,0):'core:grass' for y in range(4) for x in range(4)}
        sources=[]
        for cell in terrain:
            source,blend=ground_material(materials,cell,'core:grass',terrain,frozenset(terrain),self.definitions)
            sources.append(source)
            self.assertEqual(blend.cell,cell[:2])
        self.assertTrue(all(row==sources[0] for row in sources))
        self.assertEqual(materials.loads,1)
        self.assertEqual(len(materials.cache),2)

    def test_hard_feature_exclusion_and_mod_ground_are_tag_driven(self):
        definitions=dict(self.definitions)
        definitions['test:plain']=SimpleNamespace(tags=('surface','vegetation'),passable=True)
        definitions['test:ruin']=SimpleNamespace(tags=('surface','ruin'),passable=True)
        definitions['test:shaft']=SimpleNamespace(tags=('underground','shaft'),passable=True)
        self.assertTrue(natural_ground('test:plain',definitions))
        self.assertFalse(natural_ground('test:ruin',definitions))
        self.assertFalse(natural_ground('test:shaft',definitions))
        self.assertIsNone(ground_material(Materials(),(0,0,0),'test:ruin',{},frozenset(),definitions))
        self.assertFalse(natural_ground('unknown:unprepared',definitions))
        source,blend=ground_material(Materials(),(0,0,0),'test:plain',{},frozenset(),definitions)
        self.assertIn('grass',source[0])
        self.assertEqual(blend.widths,(0.,0.,0.,0.))
