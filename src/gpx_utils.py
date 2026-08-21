"""GPX loading and day/route configuration for the DK road trip dashboard."""
from dataclasses import dataclass, field
from math import radians, sin, cos, asin, sqrt
from pathlib import Path

import gpxpy

GPX_DIR = Path(__file__).resolve().parent.parent / "gpx-files"

# Day -> ordered list of GPX filenames making up that day's route.
# Days 4 and 5 had no driving (walking around Copenhagen), so they have no files.
DAY_FILES: dict[int, list[str]] = {
    1: ["day1_1.gpx", "day1_2.gpx"],
    2: ["day2_1.gpx", "day2_2.gpx"],
    3: ["day3.gpx"],
    4: [],
    5: [],
    6: ["day6.gpx"],
    7: ["day7.gpx"],
    8: ["day8.gpx"],
    9: ["day9.gpx"],
    10: ["day10_1.gpx", "day10_2.gpx"],
    11: ["day11.gpx"],
    12: ["day12.gpx"],
    13: ["day13.gpx"],
}

ROUTE_COLOR = "#a8492f"  # terracotta, vintage postcard style


@dataclass
class DayRoute:
    day: int
    label: str
    segments: list[list[tuple[float, float]]] = field(default_factory=list)
    distance_km: float = 0.0
    color: str = ROUTE_COLOR

    @property
    def has_route(self) -> bool:
        return len(self.segments) > 0

    @property
    def all_points(self) -> list[tuple[float, float]]:
        return [pt for seg in self.segments for pt in seg]


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


def _segment_distance_km(points: list[tuple[float, float]]) -> float:
    return sum(_haversine_km(points[i], points[i + 1]) for i in range(len(points) - 1))


def _load_segment(filename: str) -> list[tuple[float, float]]:
    path = GPX_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)
    points: list[tuple[float, float]] = []
    for track in gpx.tracks:
        for seg in track.segments:
            points.extend((p.latitude, p.longitude) for p in seg.points)
    return points


def load_day_route(day: int) -> DayRoute:
    filenames = DAY_FILES.get(day, [])
    segments = [_load_segment(fn) for fn in filenames]
    distance_km = sum(_segment_distance_km(seg) for seg in segments)
    return DayRoute(day=day, label=f"Day {day}", segments=segments, distance_km=distance_km, color=ROUTE_COLOR)


def load_all_days() -> dict[int, DayRoute]:
    return {day: load_day_route(day) for day in sorted(DAY_FILES)}
