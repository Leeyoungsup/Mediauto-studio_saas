"""Shared helpers for patch-based cell annotation workflows."""

from typing import Optional


def patch_key_from_xy(x: int, y: int) -> str:
    return f"px_{int(x)}_py_{int(y)}"


def region_points(region: dict) -> list[list[float]]:
    points = region.get("points") or region.get("coordinates") or []
    out = []
    for pt in points:
        if isinstance(pt, dict):
            x = pt.get("x")
            y = pt.get("y")
        elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
            x, y = pt[0], pt[1]
        else:
            continue
        try:
            out.append([float(x), float(y)])
        except Exception:
            continue
    return out


def bbox(points: list[list[float]]) -> Optional[tuple[float, float, float, float]]:
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def point_in_poly(x: float, y: float, poly: list[list[float]]) -> bool:
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        ):
            inside = not inside
        j = i
    return inside


def segments_intersect(a, b, c, d) -> bool:
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_seg(p, q, r):
        return (
            min(p[0], r[0]) <= q[0] <= max(p[0], r[0])
            and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])
        )

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True
    eps = 1e-9
    return (
        abs(o1) < eps and on_seg(a, c, b)
        or abs(o2) < eps and on_seg(a, d, b)
        or abs(o3) < eps and on_seg(c, a, d)
        or abs(o4) < eps and on_seg(c, b, d)
    )


def poly_intersects_rect(poly: list[list[float]], x0: float, y0: float, x1: float, y1: float) -> bool:
    if len(poly) < 3:
        return False
    poly_box = bbox(poly)
    if not poly_box:
        return False
    bx0, by0, bx1, by1 = poly_box
    if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
        return False
    rect = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    if any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in poly):
        return True
    if any(point_in_poly(x, y, poly) for x, y in rect):
        return True
    for i in range(len(poly)):
        a = poly[i]
        b = poly[(i + 1) % len(poly)]
        for j in range(4):
            if segments_intersect(a, b, rect[j], rect[(j + 1) % 4]):
                return True
    return False
