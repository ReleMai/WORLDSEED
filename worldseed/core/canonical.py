from __future__ import annotations
import hashlib,json

def canonical_hash(payload)->str:
    raw=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('utf-8')
    return hashlib.blake2b(raw,digest_size=20,person=b'WS-CANON-v1').hexdigest()
