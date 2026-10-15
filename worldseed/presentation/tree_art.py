"""WORLDSEED layered oak/pine sprites, sourced from a deterministic art bundle.

The repo stores a text-safe Base85 compressed PNG archive so content can be
reproduced from tools/build_worldspace_tree_art.py; `manifest.json` records
individual PNG hashes, anchor conventions and provenance. Loading is deferred
until the optional 2.5D path is requested. No PIL production dependency.
"""
from __future__ import annotations

from base64 import b85decode
from collections import OrderedDict
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

TREE_DIR=Path(__file__).resolve().parents[1]/'assets'/'sprites'/'worldspace'/'trees'
SPECIES=('oak','pine')
SEASONS=('spring','summer','autumn','winter')
MAX_SCALED_BYTES=48*1024*1024
MAX_SCALED_ENTRIES=64
_MAX_COMPRESSED_BYTES=1024*1024

@lru_cache(maxsize=1)
def manifest():
    data=json.loads((TREE_DIR/'manifest.json').read_text(encoding='utf-8'))
    if data.get('version')!=1 or len(data.get('entries',{}))!=12:
        raise ValueError('invalid tree art manifest')
    return data

@lru_cache(maxsize=1)
def archive_bytes():
    encoded=(TREE_DIR/'tree_layers.b85').read_text(encoding='ascii')
    if len(encoded)>_MAX_COMPRESSED_BYTES:
        raise ValueError('unbounded tree art bundle')
    return b85decode(''.join(encoded.split()))

@lru_cache(maxsize=16)
def layer_png(species,channel,season='summer'):
    if species not in SPECIES or channel not in ('trunk','shadow','crown') or season not in SEASONS:
        raise ValueError('unsupported tree art channel')
    key=f'{species}:{channel}'+(f':{season}' if channel=='crown' else '')
    row=manifest()['entries'][key]
    name=row['file']
    with ZipFile(BytesIO(archive_bytes())) as bundle:
        data=bundle.read(name)
    if sha256(data).hexdigest()!=row['sha256']:
        raise ValueError('tree art integrity mismatch: '+name)
    return data


class PygameTreeCache:
    """Bounded, window-independent source and scaled Surface cache."""
    def __init__(self,max_bytes=MAX_SCALED_BYTES):
        if type(max_bytes) is not int or not 256*1024<=max_bytes<=MAX_SCALED_BYTES:
            raise ValueError('invalid tree sprite cache budget')
        self.max_bytes=max_bytes
        self.bytes=0
        self._items=OrderedDict()

    def surface(self,pg,species,channel,season,width,height):
        if any(type(v) is not int or not 1<=v<=2048 for v in (width,height)):
            raise ValueError('invalid sprite dimensions')
        key=(species,channel,season,width,height)
        old=self._items.get(key)
        if old is not None:
            self._items.move_to_end(key)
            return old
        original=pg.image.load(BytesIO(layer_png(species,channel,season)),f'{species}_{channel}.png')
        scaled=pg.transform.smoothscale(original,(width,height))
        cost=width*height*4
        if cost>self.max_bytes:raise ValueError('single sprite exceeds cache budget')
        while self._items and (self.bytes+cost>self.max_bytes or len(self._items)>=MAX_SCALED_ENTRIES):
            k,v=self._items.popitem(last=False)
            self.bytes-=k[3]*k[4]*4
        self._items[key]=scaled
        self.bytes+=cost
        return scaled


pygame_tree_cache=PygameTreeCache()
