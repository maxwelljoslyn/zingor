"""Plane geometry for building designs (#197): lengths, areas, footprints, overlap.

Works in feet on plain float tuples and knows nothing of the database or of
the design document format; characters.design_document applies it to shapes.
The editor (static/characters/building-editor.js) repeats the wall footprint
construction in ``wall_pieces``, so the two must agree on where a wall's
faces are: a wall the editor draws flush against another's face has to pass
the server's overlap check.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

Point = tuple[float, float]
Polygon = list[Point]

# Areas under this many ft² (about 1.4 in²) count as touching, not
# overlapping: shapes meeting along a face are not rejected over floating-point
# noise or a point placed a hair inside a face, and no overlap too small to
# show at two decimal places is ever reported.
OVERLAP_TOLERANCE = 0.01
EPSILON = 1e-9
# The sharpest corner a wall may turn: below this cosine between the mitre and
# the wall's normal (a corner tighter than about 23°) the mitre runs away.
MIN_MITRE_COSINE = 0.2


class GeometryError(ValueError):
    """A shape that cannot be built: a corner too sharp or a segment too short."""


def segments(points: Sequence[Point], closed: bool) -> list[tuple[Point, Point]]:
    """Consecutive point pairs, with the closing pair when `closed`."""
    pairs = list(zip(points, points[1:]))
    if closed:
        pairs.append((points[-1], points[0]))
    return pairs


def distance(a: Point, b: Point) -> float:
    """Straight-line distance between two points."""
    return math.hypot(b[0] - a[0], b[1] - a[1])


def polyline_length(points: Sequence[Point], closed: bool) -> float:
    """Length along the points, back to the start when `closed`."""
    return sum(distance(a, b) for a, b in segments(points, closed))


def segment_spans(points: Sequence[Point], closed: bool) -> list[tuple[float, float]]:
    """Where each segment starts and ends, as distances along the polyline."""
    spans = []
    start = 0.0
    for a, b in segments(points, closed):
        end = start + distance(a, b)
        spans.append((start, end))
        start = end
    return spans


def signed_area(polygon: Sequence[Point]) -> float:
    """Shoelace area: positive when the points run counter-clockwise."""
    total = 0.0
    for (x0, y0), (x1, y1) in segments(polygon, closed=True):
        total += x0 * y1 - x1 * y0
    return total / 2


def polygon_area(polygon: Sequence[Point]) -> float:
    """Area enclosed by a simple polygon."""
    return abs(signed_area(polygon))


def cross(o: Point, a: Point, b: Point) -> float:
    """Twice the signed area of triangle o-a-b: positive when b lies left of o→a."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    """Whether p, already known to be collinear with a-b, lies between them."""
    return (
        min(a[0], b[0]) - EPSILON <= p[0] <= max(a[0], b[0]) + EPSILON
        and min(a[1], b[1]) - EPSILON <= p[1] <= max(a[1], b[1]) + EPSILON
    )


def segments_touch(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    """Whether two segments share any point, endpoints included."""
    d1 = cross(q1, q2, p1)
    d2 = cross(q1, q2, p2)
    d3 = cross(p1, p2, q1)
    d4 = cross(p1, p2, q2)
    if (d1 * d2 < 0) and (d3 * d4 < 0):
        return True
    return (
        (abs(d1) <= EPSILON and _on_segment(q1, q2, p1))
        or (abs(d2) <= EPSILON and _on_segment(q1, q2, p2))
        or (abs(d3) <= EPSILON and _on_segment(p1, p2, q1))
        or (abs(d4) <= EPSILON and _on_segment(p1, p2, q2))
    )


def is_simple(points: Sequence[Point], closed: bool) -> bool:
    """Whether the path never crosses, touches or doubles back on itself.

    Neighbouring segments may share only their common endpoint, and may not
    fold back along each other; any other two segments may not meet at all.
    """
    pairs = segments(points, closed)
    count = len(pairs)
    for i in range(count):
        for j in range(i + 1, count):
            (a, b), (c, d) = pairs[i], pairs[j]
            if j == i + 1 or (closed and i == 0 and j == count - 1):
                # Shared vertex: rule out a fold-back, where the two
                # segments are collinear and point in opposite directions.
                shared, far_i, far_j = (b, a, d) if j == i + 1 else (a, b, c)
                turn = cross(shared, far_i, far_j)
                along = (far_i[0] - shared[0]) * (far_j[0] - shared[0]) + (
                    far_i[1] - shared[1]
                ) * (far_j[1] - shared[1])
                if abs(turn) <= EPSILON and along > 0:
                    return False
                continue
            if segments_touch(a, b, c, d):
                return False
    return True


def _unit(a: Point, b: Point) -> Point:
    length = distance(a, b)
    if length <= EPSILON:
        raise GeometryError("two consecutive points coincide")
    return ((b[0] - a[0]) / length, (b[1] - a[1]) / length)


def _mitre(n0: Point, n1: Point, half: float) -> Point:
    """Offset from a corner point to the corner of its left face.

    The mitre runs along the bisector of the two segments' normals, reaching
    far enough that both faces stay `half` from their centreline.
    """
    mx, my = n0[0] + n1[0], n0[1] + n1[1]
    length = math.hypot(mx, my)
    if length <= EPSILON:
        raise GeometryError("a wall doubles back on itself")
    mx, my = mx / length, my / length
    cosine = mx * n0[0] + my * n0[1]
    if cosine < MIN_MITRE_COSINE:
        raise GeometryError("a wall turns too sharp a corner")
    reach = half / cosine
    return (mx * reach, my * reach)


def wall_pieces(
    points: Sequence[Point], thickness: float, closed: bool
) -> list[Polygon]:
    """A wall's footprint as one convex quadrilateral per segment, counter-clockwise.

    The centreline runs down the middle; each face is `thickness / 2` to
    either side. Corners inside the polyline are mitred, so neighbouring
    pieces meet along the mitre without overlapping and the pieces' total
    area is exactly length × thickness. Open ends are cut square.
    """
    pairs = segments(points, closed)
    if not pairs:
        raise GeometryError("a wall needs at least two points")
    half = thickness / 2
    directions = [_unit(a, b) for a, b in pairs]
    normals = [(-dy, dx) for dx, dy in directions]
    count = len(pairs)
    pieces = []
    for k, ((a, b), direction) in enumerate(zip(pairs, directions)):
        normal = normals[k]
        square = (normal[0] * half, normal[1] * half)
        if k > 0 or closed:
            start = _mitre(normals[k - 1], normal, half)
        else:
            start = square
        if k < count - 1 or closed:
            end = _mitre(normal, normals[(k + 1) % count], half)
        else:
            end = square
        right_start = (a[0] - start[0], a[1] - start[1])
        right_end = (b[0] - end[0], b[1] - end[1])
        left_end = (b[0] + end[0], b[1] + end[1])
        left_start = (a[0] + start[0], a[1] + start[1])
        for face_start, face_end in ((right_start, right_end), (left_start, left_end)):
            run = (face_end[0] - face_start[0]) * direction[0] + (
                face_end[1] - face_start[1]
            ) * direction[1]
            if run <= EPSILON:
                raise GeometryError("a wall segment is too short for its corners")
        pieces.append([right_start, right_end, left_end, left_start])
    return pieces


def _in_triangle(p: Point, a: Point, b: Point, c: Point) -> bool:
    """Whether p lies inside or on counter-clockwise triangle a-b-c."""
    return (
        cross(a, b, p) >= -EPSILON
        and cross(b, c, p) >= -EPSILON
        and cross(c, a, p) >= -EPSILON
    )


def triangulate(polygon: Sequence[Point]) -> list[Polygon]:
    """Split a simple polygon into counter-clockwise triangles by ear clipping."""
    points = list(polygon)
    if signed_area(points) < 0:
        points.reverse()
    remaining = list(range(len(points)))
    triangles: list[Polygon] = []
    while len(remaining) > 3:
        count = len(remaining)
        for i in range(count):
            ia, ib, ic = remaining[i - 1], remaining[i], remaining[(i + 1) % count]
            a, b, c = points[ia], points[ib], points[ic]
            turn = cross(a, b, c)
            if abs(turn) <= EPSILON:
                # A vertex partway along a straight edge adds no area.
                del remaining[i]
                break
            if turn < 0:
                continue
            if any(
                _in_triangle(points[j], a, b, c) and points[j] not in (a, b, c)
                for j in remaining
                if j not in (ia, ib, ic)
            ):
                continue
            triangles.append([a, b, c])
            del remaining[i]
            break
        else:
            raise GeometryError("a polygon crosses itself")
    if len(remaining) == 3:
        a, b, c = (points[j] for j in remaining)
        if abs(cross(a, b, c)) > EPSILON:
            triangles.append([a, b, c])
    return triangles


def _line_crossing(p: Point, q: Point, a: Point, b: Point) -> Point:
    """Where segment p-q crosses the line through a-b (the two ends straddle it)."""
    dp = cross(a, b, p)
    dq = cross(a, b, q)
    t = dp / (dp - dq)
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def convex_overlap_area(subject: Sequence[Point], clip: Sequence[Point]) -> float:
    """Area shared by two convex counter-clockwise polygons (Sutherland–Hodgman)."""
    output = list(subject)
    for a, b in segments(clip, closed=True):
        if not output:
            return 0.0
        polygon, output = output, []
        for previous, current in segments(polygon[-1:] + polygon[:-1], closed=True):
            previous_in = cross(a, b, previous) >= 0
            current_in = cross(a, b, current) >= 0
            if current_in:
                if not previous_in:
                    output.append(_line_crossing(previous, current, a, b))
                output.append(current)
            elif previous_in:
                output.append(_line_crossing(previous, current, a, b))
    return polygon_area(output) if len(output) >= 3 else 0.0


def bounds(polygon: Sequence[Point]) -> tuple[float, float, float, float]:
    """(min x, min y, max x, max y)."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return (min(xs), min(ys), max(xs), max(ys))


def overlap_area(pieces_a: Sequence[Polygon], pieces_b: Sequence[Polygon]) -> float:
    """Area shared by two shapes, each given as non-overlapping convex pieces."""
    total = 0.0
    boxes_b = [bounds(piece) for piece in pieces_b]
    for piece in pieces_a:
        ax0, ay0, ax1, ay1 = bounds(piece)
        for other, (bx0, by0, bx1, by1) in zip(pieces_b, boxes_b):
            if ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0:
                continue
            total += convex_overlap_area(piece, other)
    return total
