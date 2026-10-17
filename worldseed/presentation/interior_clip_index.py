"""Conservative indexed rectangle clipping for bounded indoor drawing.

The index is a read-only acceleration structure over *already admitted* sight
and recorded memory rectangles. It never reads undiscovered geometry.
"""
from __future__ import annotations
from math import ceil, floor
from collections import Counter


class InteriorClipIndex:
    """Return exact ordered intersections without an O(objects × tiles) scan."""

    __slots__ = ("rectangles", "_buckets", "_oversized", "_size")

    def __init__(self, rectangles, bucket_size=500):
        if bucket_size <= 0:
            raise ValueError("bucket size must be positive")
        self.rectangles = tuple(rectangles)
        self._size = bucket_size
        self._buckets = {}
        self._oversized = []
        for index, (a,b,c,d) in enumerate(self.rectangles):
            if not a < c or not b < d:
                continue
            x0,y0=floor(a/bucket_size),floor(b/bucket_size)
            x1,y1=ceil(c/bucket_size)-1,ceil(d/bucket_size)-1
            if (x1-x0+1)*(y1-y0+1)>256:
                self._oversized.append(index)
                continue
            for y in range(y0,y1+1):
                for x in range(x0,x1+1):
                    self._buckets.setdefault((x,y),[]).append(index)

    def intersect(self, bounds, padding=0):
        """Return exact intersections with optional expansion of source clips.

        Expanding a saved clip is only intended for wall-adjacent paint. Callers
        must not use padding when admitting live objects or remembered items.
        """
        a,b,c,d=bounds
        if a>=c or b>=d:
            return ()
        pad=max(0.,float(padding))
        size=self._size
        x0,y0=floor((a-pad)/size),floor((b-pad)/size)
        x1,y1=ceil((c+pad)/size)-1,ceil((d+pad)/size)-1
        indexes=set(self._oversized)
        for y in range(y0,y1+1):
            for x in range(x0,x1+1):
                indexes.update(self._buckets.get((x,y),()))
        result=[]
        for index in sorted(indexes):
            x,y,x1,y1=self.rectangles[index]
            x-=pad;y-=pad;x1+=pad;y1+=pad
            rect=(max(a,x),max(b,y),min(c,x1),min(d,y1))
            if rect[0]<rect[2] and rect[1]<rect[3]:
                result.append(rect)
        return tuple(result)


def union_rects(rects):
    """Disjoint scissor strips prevent repeated alpha along wall fragments."""
    events={}
    for a,b,c,d in rects:
        if a < c and b < d:
            events.setdefault(b,[]).append((a,c,1))
            events.setdefault(d,[]).append((a,c,-1))
    active=Counter()
    strips=[]
    previous_y=None
    for y,changes in sorted(events.items()):
        if previous_y is not None and y > previous_y:
            intervals=[]
            for (a,c),count in sorted(active.items()):
                if count <= 0:
                    continue
                if intervals and a <= intervals[-1][1]:
                    intervals[-1]=(intervals[-1][0],max(c,intervals[-1][1]))
                else:
                    intervals.append((a,c))
            for a,c in intervals:
                strips.append((a,previous_y,c,y))
        for a,c,delta in changes:
            active[(a,c)]+=delta
            if active[(a,c)] == 0:
                del active[(a,c)]
        previous_y=y
    return tuple(strips)
