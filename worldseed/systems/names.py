from __future__ import annotations
from worldseed.core.rng import PCG32
from hashlib import blake2b

HUMAN_FIRST = ["Alden","Mara","Tomas","Elias","Rowan","Ilyra","Cass","Bran","Nessa","Orin","Vera","Calder","Sera","Hale","Tarin","Lio"]
HUMAN_LAST = ["Vale","Ward","Thane","Morrow","Drust","Fen","Kerr","Ash","Voss","Mere","Dane","Rook","Stone","Kestrel"]
FEMALE_FIRST = frozenset({"Mara","Ilyra","Nessa","Vera","Sera"})
MALE_FIRST = frozenset({"Alden","Tomas","Elias","Bran","Orin","Calder","Hale","Tarin","Lio"})
PLACE_A = ["Stone","Red","Green","Black","High","Low","Ash","Raven","Silver","Iron","Oak","Mist","Sun","Frost","River","Hollow"]
PLACE_B = ["haven","ford","watch","mere","field","fall","ridge","wick","gate","rest","brook","march","stead","hold","reach"]
CULTURE_A = ["Vael","Erdan","Keth","Orun","Selen","Damar","Istral","Mor","Aven","Thyr","Cal","Nyr"]
DEITIES = ["Velor","Aestra","Namar","Thyra","Orren","Khal","Mirel","Sovar","Elun","Varos"]

def person_name(rng: PCG32) -> str:
    return f"{rng.choice(HUMAN_FIRST)} {rng.choice(HUMAN_LAST)}"

def npc_sex_for_identity(name: str, uid: str) -> str:
    """Stable assignment for existing and new NPCs without changing name RNG."""
    given=str(name).split(' ',1)[0]
    if given in FEMALE_FIRST:return 'female'
    if given in MALE_FIRST:return 'male'
    bit=blake2b(str(uid).encode('utf-8'),digest_size=1,person=b'ws-npc-sex').digest()[0]&1
    return 'female' if bit else 'male'

def place_name(rng: PCG32) -> str:
    return f"{rng.choice(PLACE_A)}{rng.choice(PLACE_B)}"

def culture_name(rng: PCG32) -> str:
    return rng.choice(CULTURE_A) + rng.choice(["an","i","ite","ari","en"])
