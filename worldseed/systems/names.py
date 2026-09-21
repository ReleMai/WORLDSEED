from __future__ import annotations
from worldseed.core.rng import PCG32

HUMAN_FIRST = ["Alden","Mara","Tomas","Elias","Rowan","Ilyra","Cass","Bran","Nessa","Orin","Vera","Calder","Sera","Hale","Tarin","Lio"]
HUMAN_LAST = ["Vale","Ward","Thane","Morrow","Drust","Fen","Kerr","Ash","Voss","Mere","Dane","Rook","Stone","Kestrel"]
PLACE_A = ["Stone","Red","Green","Black","High","Low","Ash","Raven","Silver","Iron","Oak","Mist","Sun","Frost","River","Hollow"]
PLACE_B = ["haven","ford","watch","mere","field","fall","ridge","wick","gate","rest","brook","march","stead","hold","reach"]
CULTURE_A = ["Vael","Erdan","Keth","Orun","Selen","Damar","Istral","Mor","Aven","Thyr","Cal","Nyr"]
DEITIES = ["Velor","Aestra","Namar","Thyra","Orren","Khal","Mirel","Sovar","Elun","Varos"]

def person_name(rng: PCG32) -> str:
    return f"{rng.choice(HUMAN_FIRST)} {rng.choice(HUMAN_LAST)}"

def place_name(rng: PCG32) -> str:
    return f"{rng.choice(PLACE_A)}{rng.choice(PLACE_B)}"

def culture_name(rng: PCG32) -> str:
    return rng.choice(CULTURE_A) + rng.choice(["an","i","ite","ari","en"])
