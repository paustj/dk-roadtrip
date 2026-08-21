"""Load/save per-day journal content: dates/places, free-text stories, and stops (with photos)."""
import datetime
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STOPS_FILE = DATA_DIR / "stops.yaml"
DAY_TITLES_FILE = DATA_DIR / "day_titles.yaml"
PHOTO_PINS_FILE = DATA_DIR / "photo_pins.yaml"
PHOTOS_DIR = DATA_DIR / "photos"
PINS_PHOTOS_DIR = PHOTOS_DIR / "pins"
JOURNAL_DIR = DATA_DIR / "journal"

CATEGORIES = ["Attraction", "Food", "Viewpoint", "Accommodation", "Other"]


@dataclass
class DayInfo:
    day: int
    date: datetime.date | None
    place_from: str
    place_to: str
    note: str = ""

    @property
    def title(self) -> str:
        if self.place_from and self.place_to and self.place_from != self.place_to:
            return f"{self.place_from} → {self.place_to}"
        return self.place_from or f"Day {self.day}"

    @property
    def date_label(self) -> str:
        return self.date.strftime("%a, %b %d, %Y") if self.date else ""


def _ensure_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    if not STOPS_FILE.exists():
        STOPS_FILE.write_text("{}\n", encoding="utf-8")


def load_day_info() -> dict[int, DayInfo]:
    _ensure_files()
    raw = yaml.safe_load(DAY_TITLES_FILE.read_text(encoding="utf-8")) or {}
    result = {}
    for day, entry in raw.items():
        day = int(day)
        result[day] = DayInfo(
            day=day,
            date=entry.get("date"),
            place_from=entry.get("from", ""),
            place_to=entry.get("to", ""),
            note=entry.get("note", ""),
        )
    return result


def load_journal_text(day: int) -> str:
    path = JOURNAL_DIR / f"day{day}.md"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def journal_path(day: int) -> Path:
    return JOURNAL_DIR / f"day{day}.md"


def load_stops() -> dict[int, list[dict]]:
    _ensure_files()
    raw = yaml.safe_load(STOPS_FILE.read_text(encoding="utf-8")) or {}
    return {int(day): stops for day, stops in raw.items()}


def _save_all(stops_by_day: dict[int, list[dict]]) -> None:
    _ensure_files()
    STOPS_FILE.write_text(
        yaml.safe_dump(stops_by_day, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )


def add_stop(
    day: int,
    name: str,
    lat: float,
    lon: float,
    category: str = "Other",
    notes: str = "",
    uploaded_photo=None,
) -> str:
    """Add a stop, optionally saving an uploaded photo. Returns the new stop's id."""
    stop_id = str(uuid.uuid4())[:8]
    photo_path = save_photo(day, stop_id, uploaded_photo) if uploaded_photo is not None else None

    stops_by_day = load_stops()
    day_stops = stops_by_day.setdefault(day, [])
    day_stops.append(
        {
            "id": stop_id,
            "name": name,
            "lat": lat,
            "lon": lon,
            "category": category,
            "notes": notes,
            "photo_path": photo_path,
        }
    )
    _save_all(stops_by_day)
    return stop_id


def delete_stop(day: int, stop_id: str) -> None:
    stops_by_day = load_stops()
    day_stops = stops_by_day.get(day, [])
    stops_by_day[day] = [s for s in day_stops if s["id"] != stop_id]
    _save_all(stops_by_day)


def save_photo(day: int, stop_id: str, uploaded_file) -> str:
    """Save an uploaded photo to disk and return its relative path."""
    day_dir = PHOTOS_DIR / f"day{day}"
    day_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_file.name).suffix or ".jpg"
    dest = day_dir / f"{stop_id}{suffix}"
    dest.write_bytes(uploaded_file.getbuffer())
    return str(dest.relative_to(DATA_DIR.parent))


def load_photo_pins() -> list[dict]:
    """Freely-positioned photos pinned on top of the map (independent of any day)."""
    _ensure_files()
    if not PHOTO_PINS_FILE.exists():
        return []
    return yaml.safe_load(PHOTO_PINS_FILE.read_text(encoding="utf-8")) or []


def _save_photo_pins(pins: list[dict]) -> None:
    _ensure_files()
    PHOTO_PINS_FILE.write_text(
        yaml.safe_dump(pins, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def add_photo_pin(uploaded_file, x_pct: float = 50.0, y_pct: float = 50.0) -> str:
    pin_id = str(uuid.uuid4())[:8]
    PINS_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_file.name).suffix or ".jpg"
    dest = PINS_PHOTOS_DIR / f"{pin_id}{suffix}"
    dest.write_bytes(uploaded_file.getbuffer())

    pins = load_photo_pins()
    pins.append(
        {
            "id": pin_id,
            "photo_path": str(dest.relative_to(DATA_DIR.parent)),
            "x": x_pct,
            "y": y_pct,
            "w": 140,
            "h": 140,
            "ox": 50,
            "oy": 50,
        }
    )
    _save_photo_pins(pins)
    return pin_id


def update_photo_pin(pin_id: str, **fields) -> None:
    """Merge the given fields (x/y position, w/h size, ox/oy crop offset) into a pin."""
    pins = load_photo_pins()
    for pin in pins:
        if pin["id"] == pin_id:
            pin.update(fields)
    _save_photo_pins(pins)


def delete_photo_pin(pin_id: str) -> None:
    pins = [p for p in load_photo_pins() if p["id"] != pin_id]
    _save_photo_pins(pins)
