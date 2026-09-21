from __future__ import annotations

from worldseed.core.rng import hash_u64
from worldseed.systems.history import HistorySystem
from worldseed.systems.state import BookState, LivingWorldState

OCCUPATION_KNOWLEDGE={
    'smith':['tech:smelting'], 'miner':['tech:mining'], 'healer':['knowledge:herbalism'], 'farmer':['knowledge:agriculture'],
    'scholar':['knowledge:literacy'], 'priest':['knowledge:literacy'], 'carpenter':['craft:woodworking'], 'hunter':['knowledge:tracking']
}
DISCOVERIES=['tech:steelmaking','knowledge:crop_rotation','knowledge:preservation','knowledge:surveying','knowledge:medicine','knowledge:hydraulics']
PREREQUISITES={
    'tech:steelmaking':{'tech:smelting','tech:mining'},
    'knowledge:crop_rotation':{'knowledge:agriculture'},
    'knowledge:preservation':{'knowledge:agriculture'},
    'knowledge:surveying':{'knowledge:literacy'},
    'knowledge:medicine':{'knowledge:herbalism','knowledge:literacy'},
    'knowledge:hydraulics':{'knowledge:surveying','tech:mining'},
}
FOCUS_BONUS={
    'craft':{'tech:steelmaking'},'agriculture':{'knowledge:crop_rotation','knowledge:preservation'},
    'medicine':{'knowledge:medicine'},'natural_philosophy':{'knowledge:surveying','knowledge:hydraulics'},'history':{'knowledge:literacy'}
}


class KnowledgeSystem:
    def __init__(self,state:LivingWorldState,seed:bytes,history:HistorySystem):self.state=state;self.seed=seed;self.history=history

    def bootstrap(self)->None:
        for n in self.state.npcs.values():
            for fact in OCCUPATION_KNOWLEDGE.get(n.occupation,[]):
                if fact not in n.knowledge:n.knowledge.append(fact)
            town=self.state.settlements.get(n.settlement_id)
            if town:
                for fact in n.knowledge:
                    if fact not in town.knowledge:town.knowledge.append(fact)

    def daily_update(self,minute:int)->None:
        self.bootstrap()
        day=minute//1440
        for town in self.state.settlements.values():
            scholars=[n for n in self.state.npcs.values() if n.alive and n.settlement_id==town.uid and n.occupation=='scholar']
            schools=[s for s in self.state.knowledge_schools.values() if s.settlement_id==town.uid]
            if scholars and hash_u64(self.seed,'discovery',town.uid,day)%1000<12:
                eligible=[d for d in DISCOVERIES if d not in town.knowledge and PREREQUISITES.get(d,set()).issubset(set(town.knowledge))]
                if eligible:
                    focus=schools[0].focus if schools else ''
                    weighted=[d for d in eligible for _ in range(3 if d in FOCUS_BONUS.get(focus,set()) else 1)]
                    fact=weighted[hash_u64(self.seed,'discovery-choice',town.uid,day)%len(weighted)]
                    town.knowledge.append(fact);scholars[0].knowledge.append(fact)
                    book=self._author_book(town,scholars[0],fact,minute)
                    if schools:schools[0].prestige=min(100,schools[0].prestige+2)
                    self.history.record('discovery',f'{town.name} scholars discovered {fact}; {scholars[0].name} recorded it in {book.title}.',minute,town.region_x,town.region_y,[town.uid,scholars[0].uid,book.uid],salience=45)
            self._copy_books(town,scholars,minute,day)
        self._social_transmission(minute,day)

    def _author_book(self,town,scholar,fact:str,minute:int)->BookState:
        culture=self.state.cultures.get(town.culture_id);concept='iron' if 'steel' in fact else 'home' if 'preservation' in fact else 'sun';word=culture.lexicon.get(concept,concept) if culture else concept
        bid=self.state.uid('book');title=f'{word.title()}: Notes on {fact.split(":")[-1].replace("_"," ")}'
        library=next((l for l in self.state.libraries.values() if l.settlement_id==town.uid),None);owner=library.uid if library else town.uid
        book=BookState(bid,title,scholar.name,fact,minute,town.culture_id,owner,town.culture_id,'',100);self.state.books[bid]=book
        if library and len(library.book_uids)<library.capacity:library.book_uids.append(bid)
        town.stocks['core:book']=town.stocks.get('core:book',0)+1
        return book

    def _copy_books(self,town,scholars,minute:int,day:int)->None:
        library=next((l for l in self.state.libraries.values() if l.settlement_id==town.uid),None)
        if not library or not scholars or day%10:return
        originals=[self.state.books[b] for b in library.book_uids if b in self.state.books]
        if not originals or len(library.book_uids)>=library.capacity:return
        # Writing has a physical input. If parchment is unavailable, copying stops.
        if town.stocks.get('core:parchment',0)<=0:return
        source=originals[hash_u64(self.seed,'copy-book',library.uid,day)%len(originals)]
        copies=sum(1 for b in self.state.books.values() if (b.copied_from_uid==source.uid or b.uid==source.uid) and b.knowledge==source.knowledge)
        if copies>=4:return
        town.stocks['core:parchment']-=1;uid=self.state.uid('book');copy=BookState(uid,source.title,scholars[0].name,source.knowledge,minute,source.culture_id,library.uid,source.language_id or source.culture_id,source.uid,max(40,source.condition-2))
        self.state.books[uid]=copy;library.book_uids.append(uid);town.stocks['core:book']=town.stocks.get('core:book',0)+1
        self.history.record('book_copy',f'{source.title} was copied in {library.name}.',minute,town.region_x,town.region_y,[uid,source.uid,library.uid],salience=5)

    def _social_transmission(self,minute:int,day:int)->None:
        for n in self.state.npcs.values():
            if not n.alive or not n.knowledge:continue
            peers=[p for p in self.state.npcs.values() if p.alive and p.settlement_id==n.settlement_id and p.uid!=n.uid]
            if not peers:continue
            p=peers[hash_u64(self.seed,'teach-peer',n.uid,day)%len(peers)];fact=n.knowledge[hash_u64(self.seed,'teach-fact',n.uid,day)%len(n.knowledge)]
            shared_language=max((min(v,p.language_fluency.get(lang,0)) for lang,v in n.language_fluency.items()),default=0)
            chance=max(0,20+(n.literacy+p.literacy)//10+shared_language//10-20)
            if fact not in p.knowledge and hash_u64(self.seed,'teach',n.uid,p.uid,day)%100<min(65,chance):p.knowledge.append(fact)
