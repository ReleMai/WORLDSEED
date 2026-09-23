"""Create a clean playable Dev15 source build, without saves or test runtimes."""
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]
NAME='WORLDSEED_LivingWorld_v1.0_RC14_Embodied_World_Dev15'
def main():
 out=ROOT.parent/'output';out.mkdir(exist_ok=True);dest=out/(NAME+'.zip')
 count=0
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for path in sorted(ROOT.rglob('*')):
   if not path.is_file():continue
   rel=path.relative_to(ROOT)
   if any(part.startswith('.') or part in {'__pycache__','saves','test-deps','node_modules'} for part in rel.parts):continue
   if path.suffix in {'.pyc','.pyo','.db','.db-wal','.db-shm'}:continue
   z.write(path,Path(NAME)/rel);count+=1
 with zipfile.ZipFile(dest) as z:
  assert z.testzip() is None
  for required in ['RUN_WORLDSEED.bat','worldseed/systems/swimming.py','README.md','worldseed/assets/sprites/terrain/v6_ocean_deep_00.png']:
   assert NAME+'/'+required in z.namelist()
 print(dest);print('files',count,'bytes',dest.stat().st_size)
if __name__=='__main__':main()
