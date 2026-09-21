import os,sys,time
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
sys.path[:0]=['.','tests']
import test_rc5_gameplay as helpers
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Position
from worldseed.systems.state import pos_key
from worldseed.ui.pygame_terminal import PygameTerminal
from pathlib import Path
td,db,reg,world,e,pid,sim=helpers.RC5GameplayTests().make_sim(seed=b'water-dev15-preview',gen_version=6)
g=world.generator
candidates=[]
for y in range(-512,513,16):
 for x in range(-512,513,16):
  p=WorldPos(x,y,0);el=g.sample_fields(p).elevation
  if 23800<=el<24200:
   slope=g.sample_fields(p.moved(16,0)).elevation-g.sample_fields(p.moved(-16,0)).elevation
   candidates.append((abs(slope),x,y))
_,x,y=max(candidates)
p=WorldPos(x,y,0)
# Use actual generated shore coordinate nearest this coast.
p=next((p.moved(dx,dy) for dy in range(-6,7) for dx in range(-6,7) if g._surface_terrain_base(p.moved(dx,dy))=='core:shore'),p)
e.get(pid,Position).value=p
known=[pos_key(p.x+dx,p.y+dy,0) for dy in range(-28,29) for dx in range(-50,51)]
sim._record_discovered_tiles(set(known))
if g.hydrology:g.hydrology.prepare_window(0,0,0,0,persist=False)
for dx in range(-50,51):
 for dy in range(-28,29):world.tile_at(p.moved(dx,dy))
term=PygameTerminal(1600,900);term.enter();term._tile_px=20
before=sim.state.to_dict();start=time.monotonic();term.present_game(reg,world,e,sim,pid,message='Dev15: shore > wading shallows > turquoise coastal water > shelf > deep ocean')
print('render seconds',time.monotonic()-start,'pos',p,flush=True)
Path('artifacts').mkdir(exist_ok=True)
term.pg.image.save(term.screen,'artifacts/dev15-coast.png')
assert term._water_animation_cells
pixels=term.pg.image.tobytes(term.screen,'RGB')
term._animate_idle_water(term.pg.time.get_ticks()+400)
assert pixels!=term.pg.image.tobytes(term.screen,'RGB')
term.pg.image.save(term.screen,'artifacts/dev15-coast-animated.png')
assert sim.state.to_dict()==before
# A second view uses a real prepared river corridor.
river=[]
for ry in range(64,449,8):
 for rx in range(64,449,8):
  q=WorldPos(rx,ry,0)
  if g.terrain_at(q) in {'core:river','core:river_rapids'}:
   river.append(q)
if river:
 rp=river[len(river)//2];e.get(pid,Position).value=rp
 sim._record_discovered_tiles({pos_key(rp.x+dx,rp.y+dy,0) for dx in range(-45,46) for dy in range(-25,26)})
 for dx in range(-45,46):
  for dy in range(-25,26):world.tile_at(rp.moved(dx,dy))
 term.present_game(reg,world,e,sim,pid,message='River channel: sandy gravel banks, wading margins, swimming depth and downstream currents')
 term.pg.image.save(term.screen,'artifacts/dev15-river-swimming.png')
 print('river screenshot',rp,flush=True)
term.present('WORLD CONSOLE');pixels=term.pg.image.tobytes(term.screen,'RGB');term._animate_idle_water(term.pg.time.get_ticks()+600);assert pixels==term.pg.image.tobytes(term.screen,'RGB')
print('idle animation observational and console isolation PASS',flush=True)
db.save_state(turn=sim.turn,tile_deltas={},player_id=pid,position=p,inventory={},sim_state=sim.state.to_dict());print('save verifier',db.verify(),flush=True)
term.restore();db.close();td.cleanup()
