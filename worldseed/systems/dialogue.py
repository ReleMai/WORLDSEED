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

@dataclass(frozen=True, slots=True)
class DialogueScene:
    speaker: str
    role: str
    opening: str
    context: tuple[str, ...]
    options: tuple[DialogueOption, ...]

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

    def scene(self,npc,minute:int,player_vitals,known:bool=True)->DialogueScene:
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

        options=[]
        options.append(DialogueOption("area","Ask about the area","",action="area"))
        options.append(DialogueOption("chat","Just chat",self._personal_response(npc,minute),"warm",1))
        options.append(DialogueOption("work",f"Ask about their work",self._work_response(npc,town,stressed,minute)))
        options.append(DialogueOption("trade","Trade","",action="trade"))
        options.append(DialogueOption("inspect","Inspect", "", action="inspect"))
        if hurt:
            options.append(DialogueOption("health","Mention your injuries",self._health_response(npc,minute),"concerned",1 if npc.occupation=="healer" else 0))
        if heat or bounty:
            options.append(DialogueOption("crime","Ask about the trouble around your name",self._crime_response(npc,heat,bounty,minute),"wary",-1 if npc.occupation=="guard" else 0))
        if hungry:
            options.append(DialogueOption("needs","Ask where to find food or water",self._needs_response(npc,town,minute)))
        if trust>=15 or affection>=20:
            options.append(DialogueOption("personal","Ask how they are really doing",self._personal_response(npc,minute),"warm",1))
        options.append(DialogueOption("attack","Attack", "You end the conversation and square up for violence.", "hostile", -20, "attack"))
        options.append(DialogueOption("goodbye","End conversation",self._pick(npc,"bye",["Safe travels.","Until next time.","Take care of yourself."],minute),action="goodbye"))
        return DialogueScene(npc.name if known else "Stranger",role.title(),opening,tuple(context),tuple(options))

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

    def apply_option(self,npc,option:DialogueOption)->None:
        if not option.trust_delta:return
        rel=npc.relationships.setdefault("player",{})
        rel["trust"]=max(-100,min(100,int(rel.get("trust",0))+option.trust_delta))
