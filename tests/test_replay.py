import unittest
from tools.replay import run
class ReplayTests(unittest.TestCase):
    def test_replay_hash_stable(self):
        cmds=[["move",1,0],["wait",120],["move",0,1],["gather"]]
        self.assertEqual(run('abc',cmds),run('abc',cmds))

    def test_replay_cross_process(self):
        import subprocess,sys
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        cmd=[sys.executable,str(root/'tools'/'replay.py'),str(root/'tests'/'fixtures'/'golden_replay.json')]
        a=subprocess.check_output(cmd,cwd=root,text=True).strip();b=subprocess.check_output(cmd,cwd=root,text=True).strip();self.assertEqual(a,b)
