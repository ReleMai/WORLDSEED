from __future__ import annotations
from dataclasses import dataclass
from worldseed.core.rng import hash_u64

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

@dataclass(frozen=True, slots=True)
class DialogueScene:
    speaker: str
    role: str
    opening: str
    context: tuple[str, ...]
    options: tuple[DialogueOption, ...]
    topic: str = "root"
    relationship: tuple[tuple[str, int], ...] = ()

class DialogueSystem:
    """Small state-driven storylet selector for living-world conversations.

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
        rows=[]
        for person in state.npcs.values():
            if not person.alive or person.settlement_id!=settlement_id:continue
            rel=person.relationships.get("player",{})
            if int(rel.get("familiarity",0))<=0:continue
            rows.append((int(rel.get("trust",0))+int(rel.get("affection",0)))//2)
        return sum(rows)//len(rows) if rows else 0

    def scene(self,npc,minute:int,player_vitals,known:bool=True,topic:str="root")->DialogueScene:
        phase=self._phase(minute)
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

        context=[phase.title(),role.title()]
        if routine:context.append(routine.title())
        if heat or bounty:context.append("Wanted / watched")
        if hurt:context.append("Player visibly hurt")
        if stressed:context.append("Settlement under strain")

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

        topic=topic if topic in {"root","area","personal","relations","knowledge"} else "root"
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
                DialogueOption("wellbeing","Ask how they are really doing",self._personal_response(npc,minute),"warm",1,"chat","",1,3),
                DialogueOption("family","Ask about family",self._family_response(npc,trust,minute),"warm",0,"chat","",1,2),
                DialogueOption("history","Ask about their past",self._history_response(npc,trust,minute),"neutral",1,"chat","",0,3),
                DialogueOption("back","Back to other topics","",next_topic="root"),
            ]
        elif topic=="relations":
            options=[
                DialogueOption("listen","Listen without pressing for information",self._listen_response(npc,minute),"warm",1,"chat","",1,4),
                DialogueOption("gift","Offer food or drink","",action="gift"),
                DialogueOption("trust","Ask what would earn their trust",self._trust_response(npc,trust,minute)),
                DialogueOption("back","Back to other topics","",next_topic="root"),
            ]
        else:
            options=[
                DialogueOption("area","Ask about the area","",next_topic="area"),
                DialogueOption("knowledge","Discuss nature, resources, towns, and skills","",next_topic="knowledge"),
                DialogueOption("personal","Talk about their life","",next_topic="personal"),
                DialogueOption("relations","Build the relationship","",next_topic="relations"),
                DialogueOption("work","Ask about their work",self._work_response(npc,town,stressed,minute),familiarity_delta=1),
                DialogueOption("trade","Trade","",action="trade"),
                DialogueOption("inspect","Inspect","",action="inspect"),
            ]
            if hurt:options.append(DialogueOption("health","Mention your injuries",self._health_response(npc,minute),"concerned",1 if npc.occupation=="healer" else 0,familiarity_delta=1))
            if heat or bounty:options.append(DialogueOption("crime","Ask about the trouble around your name",self._crime_response(npc,heat,bounty,minute),"wary",-1 if npc.occupation=="guard" else 0,familiarity_delta=1))
            if hungry:options.append(DialogueOption("needs","Ask where to find food or water",self._needs_response(npc,town,minute),familiarity_delta=1))
            options.append(DialogueOption("attack","Attack","You end the conversation and square up for violence.","hostile",-20,"attack",affection_delta=-15,familiarity_delta=5))
            options.append(DialogueOption("goodbye","End conversation",self._pick(npc,"bye",["Safe travels.","Until next time.","Take care of yourself."],minute),action="goodbye"))
        standing=self.settlement_standing(self.state,npc.settlement_id)
        relationship=(("trust",trust),("affection",affection),("familiarity",int(rel.get("familiarity",0))),("community",standing))
        return DialogueScene(npc.name if known else "Stranger",role.title(),opening,tuple(context),tuple(options),topic,relationship)

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
            urgent=max(npc.needs.items(),key=lambda kv:kv[1])
            if urgent[1]>=55:return f"Truthfully? {urgent[0].replace('_',' ')} has been on my mind more than I like."
        if npc.wants:return f"I keep thinking about {str(npc.wants[0]).replace('_',' ')}. Hard to know whether that is hope or foolishness."
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
            value=next((str(npc.backstory.get(k,'')) for k in ("formative_event","upbringing","birthplace","ambition") if npc.backstory.get(k)),"")
            if value:return value[:1].upper()+value[1:]+"."
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
        marker=f"{option.key}:{bucket}"
        if any(m.get("type")=="dialogue_choice" and m.get("marker")==marker for m in npc.memories):return False
        rel=npc.relationships.setdefault("player",{})
        for key,delta in (("trust",option.trust_delta),("affection",option.affection_delta),("familiarity",option.familiarity_delta)):
            low=0 if key=="familiarity" else -100
            rel[key]=max(low,min(100,int(rel.get(key,0))+int(delta)))
        npc.memories.append({"minute":int(minute),"type":"dialogue_choice","subject":"player","marker":marker,"salience":3,"valence":option.trust_delta+option.affection_delta})
        npc.memories=npc.memories[-40:]
        return True
