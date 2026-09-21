from __future__ import annotations
from worldseed.core.rng import PCG32, derive_seed
from worldseed.systems.state import LivingWorldState, HistoricEvent

class MacroHistorySystem:
    """Lazily creates coarse pre-player facts only for realized regions."""
    def __init__(self,state:LivingWorldState,seed:bytes):self.state=state;self.seed=seed
    def ensure_region(self,rx:int,ry:int,settlement_name:str,culture_name:str)->None:
        marker=f'macrohistory:{rx}:{ry}'
        if any(e.uid==marker for e in self.state.history):return
        rng=PCG32(derive_seed(self.seed,'macrohistory',rx,ry));age=80+rng.randbelow(620);found=-age*120*1440
        self.state.history.append(HistoricEvent(marker,found,'foundation',f'{settlement_name} was founded by {culture_name} settlers.',rx,ry,[settlement_name,culture_name],[],40))
        event_types=['war','famine','migration','discovery','dynasty','fire','plague']
        causes=[marker]
        for i in range(1,3+rng.randbelow(4)):
            et=rng.choice(event_types);when=found+(i*age*120*1440)//6;uid=f'{marker}:{i}'
            summaries={
                'war':f'A border war scarred the lands around {settlement_name}.','famine':f'A severe famine changed the families of {settlement_name}.',
                'migration':f'New clans migrated into the region of {settlement_name}.','discovery':f'Craftworkers near {settlement_name} mastered a forgotten technique.',
                'dynasty':f'A local ruling house rose to power in {settlement_name}.','fire':f'A great fire destroyed part of old {settlement_name}.','plague':f'A historic fever swept through {settlement_name}.'}
            self.state.history.append(HistoricEvent(uid,when,et,summaries[et],rx,ry,[settlement_name],causes[-1:],35+rng.randbelow(35)));causes.append(uid)
