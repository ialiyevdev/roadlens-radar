"""Small image/ground-plane predicates used by traffic monitoring."""

from math import hypot

Point = tuple[float, float]


def cross(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def signed_distance(point: Point, start: Point, end: Point) -> float:
    return cross(start, end, point) / hypot(end[0] - start[0], end[1] - start[1])


def segment_crossing(a: Point, b: Point, start: Point, end: Point) -> tuple[float, Point] | None:
    """Return the trajectory fraction for an intersection of both finite segments."""
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = end[0] - start[0], end[1] - start[1]
    denominator = rx * sy - ry * sx
    if abs(denominator) < 1e-10:
        return None
    qx, qy = start[0] - a[0], start[1] - a[1]
    fraction = (qx * sy - qy * sx) / denominator
    along_line = (qx * ry - qy * rx) / denominator
    if -1e-9 <= fraction <= 1 + 1e-9 and -1e-9 <= along_line <= 1 + 1e-9:
        fraction = min(1.0, max(0.0, fraction))
        return fraction, (a[0] + fraction * rx, a[1] + fraction * ry)
    return None


def polygon_area(points: list[Point] | tuple[Point, ...]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(points, (*points[1:], points[0])))) / 2


def _on_segment(a: Point, b: Point, point: Point) -> bool:
    return (abs(cross(a, b, point)) <= 1e-8
            and min(a[0], b[0]) - 1e-8 <= point[0] <= max(a[0], b[0]) + 1e-8
            and min(a[1], b[1]) - 1e-8 <= point[1] <= max(a[1], b[1]) + 1e-8)


def _intersects(a: Point, b: Point, c: Point, d: Point) -> bool:
    values = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    return ((values[0] * values[1] < 0 and values[2] * values[3] < 0)
            or _on_segment(a, b, c) or _on_segment(a, b, d)
            or _on_segment(c, d, a) or _on_segment(c, d, b))


def simple_polygon(points: list[Point]) -> bool:
    if len(set(points)) != len(points) or polygon_area(points) <= 1e-8:
        return False
    length = len(points)
    for index in range(length):
        for other in range(index + 1, length):
            if other == index + 1 or (index == 0 and other == length - 1):
                continue
            if _intersects(points[index], points[(index + 1) % length],
                           points[other], points[(other + 1) % length]):
                return False
    return True


def distance_to_segment(point: Point, start: Point, end: Point) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    fraction = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
                           / (dx * dx + dy * dy)))
    return hypot(point[0] - start[0] - fraction * dx, point[1] - start[1] - fraction * dy)


def polygon_membership(point: Point, points: list[Point]) -> tuple[bool, float]:
    """Ray-cast containment plus boundary distance for a hysteresis band."""
    inside = False
    minimum = float("inf")
    for start, end in zip(points, (*points[1:], points[0])):
        minimum = min(minimum, distance_to_segment(point, start, end))
        if (start[1] > point[1]) != (end[1] > point[1]):
            intersection_x = start[0] + (point[1] - start[1]) * (end[0] - start[0]) / (end[1] - start[1])
            if point[0] < intersection_x:
                inside = not inside
    return inside, minimum


def polygon_box_area(points: list[Point], bbox: tuple[float, float, float, float]) -> float:
    """Clip a simple polygon to an axis-aligned detection box for an image proxy."""
    clipped = list(points)
    for axis, boundary, greater in ((0, bbox[0], True), (0, bbox[2], False),
                                     (1, bbox[1], True), (1, bbox[3], False)):
        if not clipped:
            return 0.0
        output = []
        for start, end in zip(clipped, (*clipped[1:], clipped[0])):
            start_inside = start[axis] >= boundary if greater else start[axis] <= boundary
            end_inside = end[axis] >= boundary if greater else end[axis] <= boundary
            if start_inside != end_inside:
                fraction = (boundary - start[axis]) / (end[axis] - start[axis])
                output.append((start[0] + fraction * (end[0] - start[0]),
                               start[1] + fraction * (end[1] - start[1])))
            if end_inside:
                output.append(end)
        clipped = output
    return polygon_area(clipped) if len(clipped) >= 3 else 0.0
