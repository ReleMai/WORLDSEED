from __future__ import annotations

from worldseed.systems.state import LivingWorldState, HistoricEvent

DAYS_PER_YEAR = 120


class HistorySystem:
    def __init__(self,state:LivingWorldState):
        self.state=state

    def record(self,event_type:str,summary:str,minute:int,region_x:int=0,region_y:int=0,subjects:list[str]|None=None,causes:list[str]|None=None,salience:int=10)->HistoricEvent:
        ev=HistoricEvent(self.state.uid("event"),minute,event_type,summary,region_x,region_y,subjects or [],causes or [],salience)
        self.state.history.append(ev)
        self._compact_if_needed()
        return ev

    def recent(self,n:int=25)->list[HistoricEvent]:
        return self.state.history[-n:]

    def legends(self)->list[HistoricEvent]:
        return sorted((e for e in self.state.history if e.salience>=60),key=lambda e:e.salience,reverse=True)[:50]

    def _compact_if_needed(self,max_live:int=6000,batch:int=1200)->None:
        """Archive old mundane events while preserving causal legends.

        History is important, but a centuries-old world should not retain every
        low-salience market departure as an individual Python object.  Older
        mundane events become year/type aggregates; high-salience facts remain
        queryable as first-class events.
        """
        if len(self.state.history)<=max_live:return
        old=self.state.history[:batch];rest=self.state.history[batch:]
        keep=[]
        for e in old:
            if e.salience>=60:
                keep.append(e);continue
            year=e.minute//(1440*DAYS_PER_YEAR)+1
            key=f"Y{year}:{e.event_type}"
            row=self.state.history_archive.setdefault(key,{"year":year,"event_type":e.event_type,"count":0,"first_minute":e.minute,"last_minute":e.minute,"max_salience":0,"sample":""})
            row["count"]=int(row.get("count",0))+1
            row["first_minute"]=min(int(row.get("first_minute",e.minute)),e.minute)
            row["last_minute"]=max(int(row.get("last_minute",e.minute)),e.minute)
            row["max_salience"]=max(int(row.get("max_salience",0)),e.salience)
            if not row.get("sample") or e.salience>=int(row.get("max_salience",0)):
                row["sample"]=e.summary[:180]
        self.state.history=keep+rest

    def archive_rows(self,limit:int=40)->list[dict]:
        return sorted(self.state.history_archive.values(),key=lambda r:(int(r.get("year",0)),str(r.get("event_type",""))),reverse=True)[:limit]
