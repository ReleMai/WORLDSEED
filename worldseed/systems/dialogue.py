from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Mapping
from worldseed.core.rng import hash_u64
from worldseed.systems.dialogue_tree import LEGACY_TOPICS, TopicLink, load_dialogue_tree

@dataclass(frozen=True, slots=True)
class DialogueSpan:
    """A piece of speech; a topic makes its words a conversation link."""
    text: str
    topic: str = ""

@dataclass(frozen=True, slots=True)
class DialogueOption:
    key: str
    label: str
    response: str
    tone: str = "neutral"
    trust_delta: int = 0
    action: str = "chat"
    next_topic: str = ""
    affection_delta: int = 0
    familiarity_delta: int = 0
    effect_id: str = ""

@dataclass(frozen=True, slots=True)
class DialogueScene:
    speaker: str
    role: str
    opening: str
    context: tuple[str, ...]
    options: tuple[DialogueOption, ...]
    topic: str = "root"
    relationship: tuple[tuple[str, int], ...] = ()
    spans: tuple[DialogueSpan, ...] = ()
    topic_label: str = ""

class DialogueSystem:
    """State-driven, nested conversations selected from authoritative facts.

    Dialogue is selected from simulation facts instead of one fixed tree.  The
    UI can therefore ask the same NPC the same topic on another day and receive
    a different line when health, crime, schedule, settlement stress or the
    relationship has changed.
    """
    def __init__(self, state, seed: bytes):
        self.state=state;self.seed=bytes(seed or b"")

    @staticmethod
    def _phase(minute:int)->str:
        hour=(int(minute)//60)%24
        if 5<=hour<11:return "morning"
        if 11<=hour<17:return "day"
        if 17<=hour<22:return "evening"
        return "night"

    def _pick(self,npc,slot:str,rows:list[str],minute:int)->str:
        if not rows:return "..."
        bucket=int(minute)//180
        idx=hash_u64(self.seed,"dialogue",npc.uid,slot,bucket)%len(rows)
        return rows[idx]

    @staticmethod
    def settlement_standing(state,settlement_id:str)->int:
        # Legacy callers lack a local NPC index. Use a bounded witness sample
        # rather than walking the total realized population on every read.
        rows=[]
        for uid in getattr(state,"introduced_npcs",())[-128:]:
            person=state.npcs.get(uid)
            if person is None:continue
            if not person.alive or person.settlement_id!=settlement_id:continue
            rel=person.relationships.get("player",{})
            if int(rel.get("familiarity",0))<=0:continue
            rows.append((int(rel.get("trust",0))+int(rel.get("affection",0)))//2)
        return sum(rows)//len(rows) if rows else 0

    def scene(self,npc,minute:int,player_vitals,known:bool=True,topic:str="root",introduced:bool|None=None,
              facts:Mapping[str,object]|None=None)->DialogueScene:
        phase=self._phase(minute)
        if introduced is None:introduced=npc.uid in self.state.introduced_npcs
        if not known or introduced is False:
            # Do not read a stranger's job, private goals, family or social
            # metrics to decorate the introduction screen.
            options=(
                DialogueOption("introduce","Introduce myself and ask their name","",action="introduce"),
                DialogueOption("inspect","Inspect visible clothing and injuries","",action="inspect"),
                DialogueOption("goodbye","Leave without an introduction","You leave without exchanging names.",action="goodbye"),
            )
            return DialogueScene("Stranger","Unknown person","You have not exchanged introductions. What would you like to say?",(phase.title(),),options,"introduction",topic_label="Introductions")
        town=self.state.settlements.get(npc.settlement_id)
        rel=npc.relationships.get("player",{}) if isinstance(npc.relationships,dict) else {}
        trust=int(rel.get("trust",0));affection=int(rel.get("affection",0))
        heat=int(self.state.player_crime_heat.get(npc.settlement_id,0)) if npc.settlement_id else 0
        bounty=int(self.state.player_bounties.get(npc.settlement_id,0)) if npc.settlement_id else 0
        hurt=player_vitals.hp<max(25,player_vitals.max_hp//2) or player_vitals.pain>=45 or player_vitals.blood<65
        hungry=player_vitals.hunger>=70 or player_vitals.thirst>=70
        stressed=bool(town and (town.food_stress>=45 or town.unemployment>=35))
        role=str(npc.occupation or "villager").replace("_"," ")
        routine=str(npc.routine_phase or npc.goal or "").replace("_"," ")
        snapshot=self._facts(npc,town,minute,player_vitals,facts)
        tree=load_dialogue_tree()
        if topic not in LEGACY_TOPICS and topic not in tree.nodes:topic="root"

        context=[phase.title(),role.title()]
        if routine:context.append(routine.title())
        if heat or bounty:context.append("Wanted / watched")
        if hurt:context.append("Player visibly hurt")
        if stressed:context.append("Settlement under strain")
        if snapshot.get("weather.wet"):context.append("Wet weather")
        if snapshot.get("player.wealth",0)>=100:context.append("Substantial purse")
        elif snapshot.get("player.wealth",0)==0:context.append("Empty purse")

        greetings={
            "guard":["Hold there. State your business.","Keep the road clear and your hands where I can see them.","Morning. Trouble has been keeping us busy."],
            "merchant":["If you are buying, I have a moment.","Prices move faster than carts lately. What do you need?","You look like someone who has been on the road."],
            "farmer":["Fields do not wait for conversation, but I can spare a breath.","Weather has been deciding half my work for me.","Mind the rows. What did you need?"],
            "healer":["You look as though you could use a careful eye.","Tell me what hurts, not what you hope it is.","I have a little time before the next patient."],
            "smith":["Mind the sparks. What are you after?","Iron talks plainly if you listen long enough.","If it is broken, show me. If it is gossip, be quick."],
            "priest":["Peace to you. What weighs on you?","The hour is quiet enough for words.","Come in from the noise. Speak."],
            "scholar":["A question is usually more useful than an answer. What is yours?","You have interrupted a good line of thought, so make it worthwhile.","What are you trying to learn?"],
        }
        generic=["What can I do for you?","You wanted something?","We can talk for a moment."]
        opening=self._pick(npc,"opening",greetings.get(npc.occupation,generic),minute)
        if heat>=35 or bounty>0:
            opening=self._pick(npc,"crime",[
                "I know your face. Do not give me a reason to call the watch.",
                "People have been talking about you. Choose your words carefully.",
                "You are attracting the wrong kind of attention around here.",
            ],minute)
        elif hurt and npc.occupation in {"healer","guard"}:
            opening=self._pick(npc,"hurt",[
                "You are bleeding. Sit down before you fall down.",
                "You look hurt. Are you safe enough to talk?",
            ],minute)
        elif phase=="night" and npc.occupation not in {"guard","healer"}:
            opening=self._pick(npc,"night",["It is late. Make it quick.","Most decent people are asleep by now. What is it?"],minute)

        if topic in tree.nodes:
            node=tree.nodes[topic]
            if not tree.allows(topic,snapshot):
                if topic.startswith(("personal.","relations.confidence")):
                    opening=("That is personal. We do not know one another well enough yet.\n\n"
                             "I can speak about ordinary work and public concerns. Let trust grow through your conduct before asking me to open that part of my life.")
                elif topic.startswith("work.professions."):
                    opening=("That calls for experience in a different line of work. I would rather admit the limits of my knowledge than give you a confident answer I cannot support.\n\n"
                             "Ask someone who does that work, or we can return to the parts of working life I know firsthand.")
                else:
                    opening=("I do not have enough firsthand knowledge to answer that under the present circumstances. A useful answer needs a sound basis, not just a plausible story.\n\n"
                             "We can return to public matters I can speak about, and leave this detail until there is a better reason to discuss it.")
                # A denied direct/forged request must not reveal descendant
                # labels, links, private backstory or hidden proper names.
                options=[DialogueOption("back","Back to other topics","",next_topic="root")]
                spans=(DialogueSpan(opening),)
            else:
                opening="\n\n".join(tree.paragraphs(topic,snapshot,self.seed,npc.uid,minute))
                links=tuple(link for link in node.links if link.phrase in opening and tree.allows(link.topic,snapshot))
                spans=self._spans(opening,links)
                options=[DialogueOption(link.topic,tree.nodes[link.topic].label if link.topic in tree.nodes else link.topic.title(),"",next_topic=link.topic) for link in links]
                options.append(DialogueOption("back","Back to "+(tree.nodes[node.parent].label if node.parent in tree.nodes else node.parent.title()),"",next_topic=node.parent))
                options.append(DialogueOption("root","Return to the conversation","",next_topic="root"))
            standing=self._community(snapshot,npc)
            relationship=(("trust",trust),("affection",affection),("familiarity",int(rel.get("familiarity",0))),("community",standing))
            return DialogueScene(npc.name,role.title(),opening,tuple(context),tuple(options),topic,relationship,spans,node.label)
        if topic=="knowledge":
            options=[
                DialogueOption(key,label,"",action="local_knowledge") for key,label in (
                    ("animals","Ask about animals and wildlife"),
                    ("plants","Ask about plants and crops"),
                    ("resources","Ask about local resources"),
                    ("towns","Ask which other towns they know"),
                    ("skills","Ask for advice from their skills"),
                )
            ]
            options.append(DialogueOption("back","Back to other topics","",next_topic="root"))
        elif topic=="area":
            options=[
                DialogueOption("area_overview","Ask who controls this area and what it produces","",action="area"),
                DialogueOption("routes","Ask about roads and nearby settlements","",action="knowledge"),
                DialogueOption("danger","Ask what is dangerous nearby",self._danger_response(npc,town,heat,minute)),
                DialogueOption("back","Back to other topics","",next_topic="root"),
            ]
        elif topic=="personal":
            options=[
                DialogueOption("wellbeing","Ask how they are really doing",self._personal_response(npc,minute),"warm",1,"chat","personal.wellbeing",1,3),
                DialogueOption("family","Ask about family",self._family_response(npc,trust,minute),"warm",0,"chat","personal.family",1,2),
                DialogueOption("history","Ask about their past",self._history_response(npc,trust,minute),"neutral",1,"chat","personal.history",0,3),
                DialogueOption("back","Back to other topics","",next_topic="root"),
            ]
        elif topic=="relations":
            options=[
                DialogueOption("listen","Listen without pressing for information",self._listen_response(npc,minute),"warm",1,"chat","",1,4),
                DialogueOption("gift","Offer food or drink","",action="gift"),
                DialogueOption("trust","Ask what would earn their trust",self._trust_response(npc,trust,minute),next_topic="relations.trust"),
                DialogueOption("back","Back to other topics","",next_topic="root"),
            ]
        else:
            options=[
                DialogueOption("area","Ask about the area","",next_topic="area"),
                DialogueOption("knowledge","Discuss nature, resources, towns, and skills","",next_topic="knowledge"),
                DialogueOption("personal","Talk about their life","",next_topic="personal"),
                DialogueOption("relations","Build the relationship","",next_topic="relations"),
                DialogueOption("work","Ask about their work",self._work_response(npc,town,stressed,minute),next_topic="work",familiarity_delta=1),
                DialogueOption("economy","Discuss money, prices, and your circumstances","",next_topic="economy"),
                DialogueOption("trade","Trade","",action="trade"),
                DialogueOption("inspect","Inspect","",action="inspect"),
            ]
            if hurt:options.append(DialogueOption("health","Mention your injuries",self._health_response(npc,minute),"concerned",1 if npc.occupation=="healer" else 0,next_topic="health",familiarity_delta=1))
            if heat or bounty:options.append(DialogueOption("crime","Ask about the trouble around your name",self._crime_response(npc,heat,bounty,minute),"wary",-1 if npc.occupation=="guard" else 0,next_topic="crime",familiarity_delta=1))
            if hungry:options.append(DialogueOption("needs","Ask where to find food or water",self._needs_response(npc,town,minute),next_topic="needs",familiarity_delta=1))
            options.append(DialogueOption("attack","Attack","You end the conversation and square up for violence.","hostile",-20,"attack",affection_delta=-15,familiarity_delta=5))
            options.append(DialogueOption("goodbye","End conversation",self._pick(npc,"bye",["Safe travels.","Until next time.","Take care of yourself."],minute),action="goodbye"))
        opening,links=self._legacy_speech(topic,opening,npc,town,snapshot,minute)
        spans=self._spans(opening,tuple(link for link in links if tree.allows(link.topic,snapshot)))
        # The five expertise options retain their established disclosure action
        # contract; their inline words open the richer explanatory subtrees.
        if topic not in {"root","knowledge"}:
            keys={option.next_topic for option in options}
            for link in links:
                if link.topic not in keys and tree.allows(link.topic,snapshot):
                    options.insert(-1,DialogueOption(link.topic,tree.nodes[link.topic].label if link.topic in tree.nodes else link.topic.title(),"",next_topic=link.topic))
                    keys.add(link.topic)
        standing=self._community(snapshot,npc)
        relationship=(("trust",trust),("affection",affection),("familiarity",int(rel.get("familiarity",0))),("community",standing))
        return DialogueScene(npc.name if known else "Stranger",role.title(),opening,tuple(context),tuple(options),topic,relationship,spans,"Conversation" if topic=="root" else topic.title())

    @staticmethod
    def _spans(text:str,links:tuple[TopicLink,...])->tuple[DialogueSpan,...]:
        """Split speech without losing punctuation, spacing, or paragraphs."""
        candidates=[]
        for link in links:
            start=text.find(link.phrase)
            if start>=0:candidates.append((start,-len(link.phrase),link))
        cursor=0;spans=[]
        for start,_,link in sorted(candidates,key=lambda row:(row[0],row[1],row[2].topic)):
            if start<cursor:continue
            if start>cursor:spans.append(DialogueSpan(text[cursor:start]))
            spans.append(DialogueSpan(link.phrase,link.topic));cursor=start+len(link.phrase)
        if cursor<len(text):spans.append(DialogueSpan(text[cursor:]))
        return tuple(spans)

    def _facts(self,npc,town,minute,vitals,provided)->dict[str,object]:
        # External adapters can expose hundreds of authoritative scalar facts;
        # immutable content never retains the mutable simulation or snapshot.
        facts={key:value for key,value in (provided or {}).items() if isinstance(key,str) and
               isinstance(value,(str,int,float,bool)) and (not isinstance(value,float) or math.isfinite(value))}
        relationship=npc.relationships.get("player",{})
        for key in ("trust","affection","familiarity"):
            value=int(relationship.get(key,0));facts["relationship."+key]=value;facts["player."+key]=value
        for key in ("hp","max_hp","hunger","thirst","pain","blood","stamina","body_temp"):
            facts["player."+key]=getattr(vitals,key,100 if key=="stamina" else 50 if key=="body_temp" else 0)
        facts["player.hurt"]=vitals.hp<max(25,vitals.max_hp//2) or vitals.pain>=45 or vitals.blood<65
        facts["player.hungry"]=vitals.hunger>=70 or vitals.thirst>=70
        facts["player.crime_heat"]=int(self.state.player_crime_heat.get(npc.settlement_id,0))
        facts["player.bounty"]=int(self.state.player_bounties.get(npc.settlement_id,0))
        facts.setdefault("player.wealth",0)
        if isinstance(facts["player.wealth"],bool) or not isinstance(facts["player.wealth"],(int,float)):
            facts["player.wealth"]=0
        facts["npc.occupation"]=npc.occupation
        facts["npc.health"]=getattr(npc,"hp",100)
        for key in ("age","hp","hunger","thirst","rest","wealth","literacy","routine_phase","goal"):
            facts["npc."+key]=getattr(npc,key,0 if key not in {"routine_phase","goal"} else "")
        facts["npc.hungry"]=facts["npc.hunger"]>=70
        facts["npc.thirsty"]=facts["npc.thirst"]>=70
        facts["npc.tired"]=facts["npc.rest"]>=70
        facts["npc.hurt"]=facts["npc.hp"]<70
        facts["npc.family_count"]=len(npc.parents)+len(npc.children)+int(bool(npc.spouse_uid))
        for trait in getattr(npc,"traits",()):
            facts["npc.traits."+trait]=True;facts["npc.trait."+trait]=True
        facts.setdefault("npc.trait.suspicious",False)
        for key,value in getattr(npc,"needs",{}).items():facts["npc.needs."+key]=value
        for key in ("hunger","thirst","rest"):facts.setdefault("npc.needs."+key,facts["npc."+key])
        for key,value in getattr(npc,"skills",{}).items():facts["npc.skills."+key]=value
        facts["town.present"]=facts["settlement.has_town"]=bool(town)
        for key in ("food_stress","unemployment","prosperity","wealth","population","sanitation","homeless","quarantine_level","religious_tension","frontier_status","border_pressure","patrol_pressure"):
            value=getattr(town,key,0) if town else 0
            if isinstance(value,(str,int,float,bool)):facts["town."+key]=value;facts["settlement."+key]=value
        facts["town.unsanitary"]=bool(town and town.sanitation<35)
        facts["town.quarantined"]=bool(town and town.quarantine_level>0)
        facts["town.housing_shortage"]=bool(town and (town.homeless>0 or town.population>town.housing_capacity))
        facts["player.exhausted"]=facts["player.stamina"]<=20
        facts["player.cold"]=facts["player.body_temp"]<=25
        facts["player.hot"]=facts["player.body_temp"]>=75
        facts["time.phase"]=self._phase(minute)
        facts.setdefault("environment.phase",facts["time.phase"])
        facts["weather.wet"]=bool(facts.get("environment.rain",0) or facts.get("environment.wetness",0) or facts.get("weather.wet",False))
        return facts

    def _community(self,facts,npc):
        if "relationship.community" in facts:return int(facts["relationship.community"])
        return self.settlement_standing(self.state,npc.settlement_id)

    def _legacy_speech(self,topic,greeting,npc,town,facts,minute):
        links=[]
        def link(phrase,target):links.append(TopicLink(phrase,target));return phrase
        if topic=="root":
            text=(greeting+"\n\nThere is always more behind a short answer. We can talk about "+link("the area","area")+", "+
                  link("my life","personal")+", or "+link("what trust means","relations")+". If you want practical knowledge, ask about "+
                  link("nature and skills","knowledge")+"; "+link("my work","work")+" touches all of those things in one way or another.")
            if facts["player.bounty"] or facts["player.crime_heat"]:
                text+="\n\nBefore anything else, "+link("the attention following you","crime")+" changes how openly people will speak. A purse cannot settle every suspicion."
            elif facts["player.hurt"]:
                text+="\n\nI can see "+link("your injuries","health")+". Pain and blood loss make a long conversation harder; shelter and safety come first."
            if facts["player.hurt"] and not any(l.topic=="health" for l in links):
                text+=" Your "+link("injuries","health")+" need attention as well."
            if facts["player.hungry"]:text+="\n\nWe should also consider "+link("food and water","needs")+" before you push yourself farther."
            if facts["player.wealth"]>=100:
                text+="\n\nYou have means, but "+link("money and obligations","economy")+" are different things. Someone with choices can afford patience; people with empty stores cannot."
            elif facts["player.wealth"]<=0:
                text+="\n\nAn empty purse narrows your choices. We can discuss "+link("making ends meet","economy")+", though goodwill still depends on how you act."
            else:text+="\n\nIf the road is costing more than you expected, we can discuss "+link("prices and your purse","economy")+"."
            if facts["weather.wet"]:text+=" Rain changes the work, the journey, and what you need to keep dry."
            if facts["settlement.food_stress"]>=45:text+=" Short supplies are pressing on ordinary decisions here; listen for the causes behind complaints."
            return text,tuple(links)
        if topic=="area":
            text=("An area is more than the houses you can see. "+link("Roads and crossings","area.roads")+
                  " decide which supplies arrive, while "+link("local dangers","area.dangers")+" determine how safely people can move. Weather and available work change those answers.\n\n"
                  "Ask for public facts before assuming that any field, door, or store is open to travelers. The watch and the people doing the work usually know the limits of what they can promise.")
        elif topic=="personal":
            text=(self._personal_response(npc,minute)+"\n\nYou can ask about "+link("how I am managing","personal.wellbeing")+
                  ". "+link("Family","personal.family")+" is a more personal matter, and "+link("my past","personal.history")+
                  " takes greater trust. A conversation is easier when neither person feels every silence must be filled.\n\n"
                  "People have immediate worries and longer hopes. I will tell you what I can, but the right to ask does not oblige another person to share every detail.")
        elif topic=="relations":
            text=("Knowing a name is the beginning of a relationship. "+link("Earning trust","relations.trust")+
                  " takes conduct that remains decent when no one is rewarding it. Listening and respecting boundaries matter more than repeating a pleasing phrase.\n\n"
                  "There are things I would speak about "+link("in confidence","relations.confidence")+
                  " once we know each other better. Gifts may help with an actual need, but you cannot buy an obligation to reveal someone else's life.")
        else:
            text=("Practical knowledge starts with observations. We can discuss "+link("animals","knowledge.animals")+", "+link("plants","knowledge.plants")+
                  ", or "+link("resources","knowledge.resources")+" and how to judge what you find. The same landscape can support very different work when the season or tools change.\n\n"
                  "I can explain how people think about "+link("other towns","knowledge.towns")+" and "+link("skills","knowledge.skills")+
                  ". Specific names and discoveries still need an explicit question; general advice is not proof that an unseen place or creature is nearby.")
        # Legacy groups remain stable entry points while authored direct-child
        # additions stay reachable automatically. This walks bounded cached
        # content, never simulation populations or undiscovered world records.
        tree=load_dialogue_tree()
        linked={item.topic for item in links}
        extra=[]
        for node in sorted(tree.nodes.values(),key=lambda row:row.uid):
            if node.parent==topic and node.uid not in linked and tree.allows(node.uid,facts):
                extra.append(link(node.label.lower(),node.uid))
        if extra:text+="\n\nThere is more to that question: we can discuss "+", ".join(extra)+". Follow whichever detail matters to you, and we can take it one part at a time."
        return text,tuple(links)

    def _work_response(self,npc,town,stressed,minute):
        role=npc.occupation
        special={
            "guard":"Most of the job is watching before trouble becomes violence.",
            "merchant":"Stock, trust, and roads. Lose any one of those and trade dries up.",
            "farmer":"Soil, rain, pests, timing. The harvest is the sum of small decisions.",
            "healer":"Clean water and time save more people than miracles do.",
            "smith":"Good work starts with fuel, sound metal, and patience at the right heat.",
            "fisher":"Water changes by the hour. You learn to read current before you read the fish.",
            "priest":"People come for rites, but most stay because they need someone to listen.",
            "scholar":"Knowledge is easier to store than to keep true.",
        }
        base=special.get(role,f"I do the work expected of a {str(role).replace('_',' ')}.")
        if stressed:return base+" Lately everyone is doing more with less."
        return base

    def _town_response(self,npc,town,stressed,minute):
        if not town:return "I am not tied closely enough to a settlement to answer that."
        if stressed:return f"{town.name} is holding together, but shortages and work are wearing people down."
        rows=[f"{town.name} has its problems, but people here know one another.",f"Roads, work, and weather shape {town.name} more than speeches do.",f"If you stay in {town.name}, learn who owns what and who watches which door."]
        return self._pick(npc,"town",rows,minute)

    def _health_response(self,npc,minute):
        if npc.occupation=="healer":return "Do not ignore blood loss, fever, or worsening pain. Rest somewhere sheltered and let me see what supplies you have."
        if npc.occupation=="guard":return "Get somewhere safe first. A wounded traveler is an easy target after dark."
        return "You look rough. There may be a healer nearby; at least get out of the weather and rest."

    def _crime_response(self,npc,heat,bounty,minute):
        if npc.occupation=="guard":return "Keep your distance from private property and obey orders. More trouble will bring a search, not a conversation."
        return "People remember theft and forced doors. If you want the talk to die down, stop feeding it."

    def _needs_response(self,npc,town,minute):
        if town and town.food_stress>=55:return "Food is tight. The market may have something, but do not expect generous prices."
        if npc.occupation in {"farmer","merchant"}:return "Try the market or the working farms. Water is usually easier to find than a full meal."
        return "Ask around the market and wells. Someone there will know what is available today."

    def _personal_response(self,npc,minute):
        if npc.needs:
            visible={key:value for key,value in npc.needs.items() if key in {"hunger","thirst","rest","social","safety","warmth","health"} and isinstance(value,(int,float))}
            urgent=max(visible.items(),key=lambda kv:(kv[1],kv[0])) if visible else ("rest",0)
            if urgent[1]>=55:return f"Truthfully? {urgent[0].replace('_',' ')} has been on my mind more than I like."
        if npc.wants:return "I have hopes beyond the next day's work. I am still deciding which of them to share."
        return self._pick(npc,"personal",["I am managing. That is enough for today.","Some days are quieter inside than others."],minute)

    def _danger_response(self,npc,town,heat,minute):
        if heat>0:return "Right now, the attention following you is the danger most people here notice first."
        if town and town.food_stress>=45:return "Short supplies make roads and tempers less safe. Keep your pack close."
        if npc.occupation=="guard":return "Watch the roads after dark, and do not assume every quiet stretch is empty."
        return self._pick(npc,"danger",["Travel prepared and ask the watch before taking an unfamiliar road.","Most trouble starts where roads thin and witnesses disappear."],minute)

    def _family_response(self,npc,trust,minute):
        relatives=len(npc.parents)+len(npc.children)+(1 if npc.spouse_uid else 0)
        if trust<8:return "That is personal. We do not know one another well enough yet."
        if relatives:return f"Family ties run through much of my life. There are {relatives} people I count close enough to name as family."
        return "I do not have close family here, or none I am ready to speak about."

    def _history_response(self,npc,trust,minute):
        if trust<18:return "Some history is earned, not requested. Give me time to know you."
        if npc.backstory:
            # Raw backstory may contain undiscovered people or places. General
            # recollections do not constitute explicit knowledge disclosure.
            if npc.backstory.get("formative_event"):return "There was a time that changed what I expect from people. I judge promises by what follows them now."
            if npc.backstory.get("upbringing"):return "The way I was raised still shapes how I work and how slowly I place my trust."
            if npc.backstory.get("birthplace"):return "I remember the place I came from, but a place name alone would not explain the life I had there."
            if npc.backstory.get("ambition"):return "I have carried some hopes for a long time. Work and difficult seasons have changed how I think about them."
        return "My past is mostly ordinary work, hard seasons, and people I remember."

    def _listen_response(self,npc,minute):
        return self._pick(npc,"listen",["They relax a little when it becomes clear you are actually listening.","You give them room to speak without turning every word into a demand."],minute)

    def _trust_response(self,npc,trust,minute):
        if trust>=35:return "Keep your word, respect private ground, and help when the cost is real. You have done better than most."
        if "suspicious" in npc.traits:return "Do not pry. Keep your word twice before expecting me to believe it once."
        return "Listen, respect our homes, and offer help without treating kindness like a purchase."

    def apply_option(self,npc,option:DialogueOption,minute:int)->bool:
        if not (option.trust_delta or option.affection_delta or option.familiarity_delta):return False
        bucket=int(minute)//180
        effect=option.effect_id or option.key
        marker=f"dialogue:v2:{npc.uid}:player:{effect}:{bucket}"
        if any(m.get("type")=="dialogue_choice" and m.get("marker")==marker for m in npc.memories):return False
        rel=npc.relationships.setdefault("player",{})
        positive=option.trust_delta>0 or option.affection_delta>0 or option.familiarity_delta>0
        spent=int(rel.get("dialogue_positive_bucket",-1))==bucket
        changes=tuple((key,0 if spent and delta>0 else delta) for key,delta in
                      (("trust",option.trust_delta),("affection",option.affection_delta),("familiarity",option.familiarity_delta)))
        if not any(delta for _,delta in changes):return False
        for key,delta in changes:
            low=0 if key=="familiarity" else -100
            rel[key]=max(low,min(100,int(rel.get(key,0))+int(delta)))
        # A single positive interaction budget survives bounded memory pruning
        # and save/load, so cycling topic aliases cannot farm relationship gains.
        if positive and not spent:rel["dialogue_positive_bucket"]=bucket
        valence=sum(delta for key,delta in changes if key in {"trust","affection"})
        npc.memories.append({"minute":int(minute),"type":"dialogue_choice","subject":"player","marker":marker,"salience":3,"valence":valence})
        npc.memories=npc.memories[-40:]
        return True
