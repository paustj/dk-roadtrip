"""Load/save per-day journal content: dates/places, free-text stories, and stops (with photos)."""
import datetime
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml
from PIL import Image, ImageOps

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STOPS_FILE = DATA_DIR / "stops.yaml"
DAY_TITLES_FILE = DATA_DIR / "day_titles.yaml"
PHOTOS_DIR = DATA_DIR / "photos"
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


# ---------- day photos ----------
# Each day has a folder data/photos/dayN with resized photos and a thumbs/ subfolder.
# The folder is the source of truth, so photos can also be added by copying files in.

PHOTO_MAX = 1600  # px, longest side of the stored photo
THUMB_MAX = 480
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def day_photo_dir(day: int) -> Path:
    return PHOTOS_DIR / f"day{day}"


def list_day_photos(day: int) -> list[dict]:
    folder = day_photo_dir(day)
    if not folder.exists():
        return []
    photos = []
    for f in sorted(folder.iterdir()):
        if f.is_file() and f.suffix.lower() in PHOTO_EXTS:
            thumb = folder / "thumbs" / f"{f.stem}.jpg"
            photos.append({"id": f.stem, "path": f, "thumb": thumb if thumb.exists() else f})
    return photos


def count_day_photos(day: int) -> int:
    return len(list_day_photos(day))


def _save_resized(img: Image.Image, dest: Path, max_side: int) -> None:
    img = img.copy()
    img.thumbnail((max_side, max_side))
    img.save(dest, "JPEG", quality=85, optimize=True)


def add_day_photo(day: int, uploaded_file) -> str:
    """Store an uploaded photo for a day, rotated upright and shrunk. Returns its id."""
    folder = day_photo_dir(day)
    (folder / "thumbs").mkdir(parents=True, exist_ok=True)
    # timestamp first so photos list in upload order
    photo_id = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    img = ImageOps.exif_transpose(Image.open(uploaded_file)).convert("RGB")
    _save_resized(img, folder / f"{photo_id}.jpg", PHOTO_MAX)
    _save_resized(img, folder / "thumbs" / f"{photo_id}.jpg", THUMB_MAX)
    return photo_id


def delete_day_photo(day: int, photo_id: str) -> None:
    for p in list_day_photos(day):
        if p["id"] == photo_id:
            p["path"].unlink(missing_ok=True)
            if p["thumb"] != p["path"]:
                p["thumb"].unlink(missing_ok=True)
