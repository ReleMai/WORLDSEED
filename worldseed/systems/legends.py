from __future__ import annotations
from worldseed.core.rng import PCG32, derive_seed
from worldseed.systems.state import LivingWorldState, CreatureState
from worldseed.systems.history import HistorySystem

MONSTER_PREFIX=['Grim','Hollow','Red','Ash','Black','Old','Pale','Iron','Crooked','Night']
MONSTER_SUFFIX=['Eye','Maw','Claw','Back','Tooth','Horn','Shadow','Hide','Skull','Fang']
class LegendSystem:
    def __init__(self,state:LivingWorldState,seed:bytes,history:HistorySystem):self.state=state;self.seed=seed;self.history=history
    def credit_kill(self,c:CreatureState,minute:int,victim:str)->None:
        c.kills+=1
        if not c.notable:
            rng=PCG32(derive_seed(self.seed,'legend-name',c.uid));c.notable=True;c.name=f'{rng.choice(MONSTER_PREFIX)} {rng.choice(MONSTER_SUFFIX)}';c.bounty=80
            self.history.record('monster_legend',f'{c.name}, a {c.species_id}, became feared after killing {victim}.',minute,c.x//512,c.y//512,[c.uid],salience=70)
        else:
            c.bounty+=40;self.history.record('monster_kill',f'{c.name} claimed another victim: {victim}.',minute,c.x//512,c.y//512,[c.uid],salience=min(95,60+c.kills*5))
