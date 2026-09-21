import os, sqlite3, json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ['SDL_VIDEODRIVER']='dummy'
os.environ['SDL_AUDIODRIVER']='dummy'
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World
from worldseed.world.region_blocks import RegionBlockPlanner
from worldseed.ui.pygame_terminal import PygameTerminal
p=Path('saves/New_World.db').resolve()
db=WorldDatabase(p,sqlite3.connect(p.as_uri()+'?mode=ro',uri=True))
state=db.load_sim_state()
row=db.connection.execute("SELECT payload_json FROM components WHERE kind='Position' LIMIT 1").fetchone()
pos=WorldPos(**json.loads(row[0]))
reg=ContentRegistry.load(DATA_DIR)
world=World(WorldGenerator(bytes.fromhex(db.get_meta('world_seed')),reg,db.get_meta('worldgen_version')),reg,db,auto_hydrology=False)
known=set(state.get('discovered_settlements',[]))|set(state.get('visited_settlements',[]))
towns=[SimpleNamespace(**v) for uid,v in state['settlements'].items() if uid in known]
sim=SimpleNamespace(world=world,player_pos=pos,discovered_tiles_set=set(state['discovered_tiles']),known_settlements=lambda:towns,visited_settlement_ids=lambda:set(state.get('visited_settlements',[])),region_planner=RegionBlockPlanner(world))
t=PygameTerminal(1280,800);t.enter()
with patch.object(world.generator,'generate_chunk',side_effect=AssertionError('generation')), patch.object(sim.region_planner,'_generate',side_effect=AssertionError('planning')):
    t.present_region_map(sim)
    t.pg.image.save(t.screen,'artifacts/region-map-fixed.png')
print('Discovered tiles:',len(sim.discovered_tiles_set),'DB writes:',db.connection.total_changes)
t.pg.quit();db.close()
