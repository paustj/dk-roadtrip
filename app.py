import base64
import sys
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import data_store  # noqa: E402
from gpx_utils import DayRoute, load_all_days  # noqa: E402

st.set_page_config(page_title="Denmark road trip", layout="wide")

CARD_BG = "#000000"
CARD_BORDER = "#0f3460"
ROUTE_COLOR = "#b026ff"
TEXT_COLOR = "#f9f9f9"
MUTED_TEXT = "#9fb0d8"
MARKER_FILL = "#000000"
MARKER_OUTLINE = "#ffffff"
DK_CENTER = (56.0, 10.5)
MAP_HEIGHT = 900
MAP_TILES = "CartoDB dark_matter"
MAP_ZOOM = 8

st.markdown(
    f"""
    <style>
    div.block-container{{padding:0 !important;max-width:100% !important;}}
    header[data-testid="stHeader"]{{background:transparent;}}
    iframe{{display:block;}}
    .st-key-board_upload_container{{
        position:fixed;bottom:20px;right:20px;z-index:600;width:260px;
        background:{CARD_BG};border:2px solid {ROUTE_COLOR};border-radius:10px;
        padding:10px 14px;box-shadow:0 4px 16px rgba(0,0,0,0.5);
    }}
    div[data-testid="stButton"] button, div[data-testid="stFileUploaderDropzone"] button {{
        background-color:{CARD_BG} !important;
        border:2px solid {ROUTE_COLOR} !important;
        color:{TEXT_COLOR} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# (day whose first segment ends here, day whose next segment starts here) -> ferry label.
# The gap between those two points is drawn as a dashed ferry line instead of left blank.
FERRY_CROSSINGS: list[dict] = [
    {"day": 1, "after_segment": 0, "label": "Ferry: Aarhus → Sjællands Odde"},
    {"day": 2, "after_segment": 0, "label": "Ferry: Rørvig → Hundested"},
    {"day": 10, "after_segment": 0, "label": "Ferry crossing (Langelandsbælt)"},
]


@st.cache_data
def get_days() -> dict[int, DayRoute]:
    return load_all_days()


def is_owner() -> bool:
    return bool(st.session_state.get("is_owner"))


def render_owner_gate() -> None:
    if is_owner():
        st.caption("🔓 Editing unlocked")
        if st.button("Lock", key="lock_btn"):
            st.session_state["is_owner"] = False
            st.rerun()
        return

    pw = st.text_input("Password to edit", type="password", key="owner_pw", label_visibility="collapsed", placeholder="Password to edit")
    if st.button("Unlock editing", key="unlock_btn"):
        expected = st.secrets.get("board_password", "")
        if expected and pw == expected:
            st.session_state["is_owner"] = True
            st.rerun()
        else:
            st.error("Wrong password.")


CENTER_LAT_OFFSET = -0.4  # shifts the map's center point south (negative = down)


def routes_center(days: dict[int, DayRoute]) -> tuple[float, float]:
    all_points = [pt for d in days.values() for pt in d.all_points]
    if not all_points:
        return DK_CENTER
    lats = [p[0] for p in all_points]
    lons = [p[1] for p in all_points]
    return (min(lats) + max(lats)) / 2 + CENTER_LAT_OFFSET, (min(lons) + max(lons)) / 2


def _photo_data_uri(relative_path: str) -> str | None:
    full_path = Path(__file__).resolve().parent / relative_path
    if not full_path.exists():
        return None
    b64 = base64.b64encode(full_path.read_bytes()).decode("ascii")
    ext = full_path.suffix.lstrip(".").lower() or "jpeg"
    return f"data:image/{ext};base64,{b64}"


def build_popup_html(day: int, info: data_store.DayInfo, route: DayRoute, stops: list[dict]) -> str:
    meta_bits = [b for b in [info.date_label, info.note] if b]
    meta_line = " · ".join(meta_bits)

    story_html = ""
    story = data_store.load_journal_text(day)
    if story:
        preview = story if len(story) <= 220 else story[:220].rsplit(" ", 1)[0] + "…"
        story_html = f"<div style='margin-top:8px;font-size:12.5px;color:#dfe6f5;line-height:1.4;'>{preview}</div>"

    photos_html = ""
    thumbs = [_photo_data_uri(s["photo_path"]) for s in stops if s.get("photo_path")][:3]
    thumbs = [uri for uri in thumbs if uri]
    if thumbs:
        imgs = "".join(
            f"<img src='{uri}' style='width:56px;height:56px;object-fit:cover;border-radius:4px;"
            f"margin-right:4px;border:1px solid {CARD_BORDER};'>"
            for uri in thumbs
        )
        photos_html = f"<div style='margin-top:8px;'>{imgs}</div>"

    return f"""
    <div style="background:{CARD_BG};color:{TEXT_COLOR};padding:12px 14px;border-radius:8px;
                border:2px solid {ROUTE_COLOR};min-width:220px;max-width:260px;
                font-family:'Space Grotesk',-apple-system,sans-serif;">
      <div style="font-weight:700;font-size:15px;">Day {day} &middot; {info.title}</div>
      <div style="font-size:12px;color:{MUTED_TEXT};margin-top:2px;">{meta_line}</div>
      <div style="font-size:13px;margin-top:8px;color:{ROUTE_COLOR};font-weight:700;">{route.distance_km:.0f} km</div>
      {story_html}
      {photos_html}
    </div>
    """


def build_overlay_box_html(days: dict[int, DayRoute], day_info: dict[int, data_store.DayInfo]) -> str:
    total_km = sum(d.distance_km for d in days.values())
    dates = [info.date for info in day_info.values() if info.date]
    date_range = f"{min(dates):%B %d} – {max(dates):%B %d, %Y}" if dates else ""

    return f"""
    <div style="position:absolute;top:14px;left:14px;z-index:1000;background:{CARD_BG};color:{TEXT_COLOR};
                padding:10px 18px;border-radius:6px;border:2px solid {ROUTE_COLOR};
                font-family:'Space Grotesk',-apple-system,sans-serif;box-shadow:0 2px 10px rgba(0,0,0,0.45);">
      <div style="font-size:20px;font-weight:800;letter-spacing:0.5px;">Denmark Roadtrip '26</div>
      <div style="font-size:12px;color:{MUTED_TEXT};margin-top:2px;">{date_range}</div>
      <div style="font-size:13px;margin-top:6px;">
        <span style="color:{ROUTE_COLOR};font-weight:700;">{total_km:.0f} km</span>
        <span style="color:{MUTED_TEXT};"> · {len(days)} days</span>
      </div>
    </div>
    """


def build_map(
    days: dict[int, DayRoute],
    day_info: dict[int, data_store.DayInfo],
    all_stops: dict[int, list[dict]],
) -> folium.Map:
    m = folium.Map(
        location=routes_center(days),
        zoom_start=MAP_ZOOM,
        min_zoom=MAP_ZOOM,
        zoomSnap=0.5,
        tiles=MAP_TILES,
        zoom_control=False,
    )
    m.get_root().header.add_child(
        folium.Element(
            '<link rel="stylesheet" '
            'href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap">'
        )
    )

    for day, route in days.items():
        if not route.has_route:
            continue
        info = day_info[day]
        stops = all_stops.get(day, [])
        for segment in route.segments:
            folium.PolyLine(
                segment,
                color=ROUTE_COLOR,
                weight=4,
                opacity=0.9,
                popup=folium.Popup(build_popup_html(day, info, route, stops), max_width=300),
                tooltip=f"Day {day} · {info.title}",
            ).add_to(m)

        for crossing in FERRY_CROSSINGS:
            if crossing["day"] != day:
                continue
            i = crossing["after_segment"]
            if i + 1 >= len(route.segments):
                continue
            gap = [route.segments[i][-1], route.segments[i + 1][0]]
            folium.PolyLine(
                gap,
                color=ROUTE_COLOR,
                weight=3,
                opacity=0.9,
                dash_array="2, 10",
                popup=folium.Popup(
                    f"<div style='background:{CARD_BG};color:{TEXT_COLOR};padding:8px 12px;"
                    f"border:2px solid {ROUTE_COLOR};border-radius:6px;font-family:'Space Grotesk',sans-serif;"
                    f"font-size:13px;'>⛴ {crossing['label']}</div>",
                    max_width=250,
                ),
                tooltip=crossing["label"],
            ).add_to(m)

        start, end = route.segments[0][0], route.segments[-1][-1]
        folium.CircleMarker(
            start,
            radius=5,
            color=MARKER_OUTLINE,
            weight=1.5,
            fill=True,
            fill_color=MARKER_FILL,
            fill_opacity=1,
            tooltip=f"Day {day} start — {info.place_from}",
        ).add_to(m)
        folium.CircleMarker(
            end,
            radius=5,
            color=MARKER_OUTLINE,
            weight=1.5,
            fill=True,
            fill_color=MARKER_FILL,
            fill_opacity=1,
            tooltip=f"Day {day} end — {info.place_to}",
        ).add_to(m)

    m.get_root().html.add_child(folium.Element(build_overlay_box_html(days, day_info)))

    return m


_PHOTO_BOARD_JS = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component

  let root = parentElement.querySelector('#photo-board-root')
  if (!root) {
    root = document.createElement('div')
    root.id = 'photo-board-root'
    root.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;pointer-events:none;z-index:500;'
    parentElement.appendChild(root)
  }
  root.innerHTML = ''

  const photos = (data && data.photos) || []
  const isOwner = !!(data && data.is_owner)

  photos.forEach((photo) => {
    const w = photo.w || 140
    const h = photo.h || 140
    const ox = photo.ox != null ? photo.ox : 50
    const oy = photo.oy != null ? photo.oy : 50

    const wrap = document.createElement('div')
    wrap.style.cssText = `position:absolute;left:${photo.x}%;top:${photo.y}%;transform:translate(-50%,-50%);
      width:${w}px;height:${h}px;pointer-events:${isOwner ? 'auto' : 'none'};touch-action:none;`

    const img = document.createElement('img')
    img.src = photo.src
    img.draggable = false
    img.style.cssText = `width:100%;height:100%;object-fit:cover;object-position:${ox}% ${oy}%;
      border-radius:6px;border:3px solid #f9f9f9;box-shadow:0 4px 14px rgba(0,0,0,0.5);display:block;cursor:grab;`
    wrap.appendChild(img)

    if (!isOwner) {
      root.appendChild(wrap)
      return
    }

    const delBtn = document.createElement('button')
    delBtn.textContent = '\\u00d7'
    delBtn.title = 'Delete'
    delBtn.style.cssText = 'position:absolute;top:-10px;right:-10px;width:22px;height:22px;border-radius:50%;background:#e94560;color:#fff;border:2px solid #fff;cursor:pointer;font-size:14px;line-height:1;padding:0;z-index:3;'
    delBtn.onclick = (e) => {
      e.stopPropagation()
      setTriggerValue('deleted', photo.id)
    }
    wrap.appendChild(delBtn)

    let panMode = false
    const cropBtn = document.createElement('button')
    cropBtn.textContent = '\\u2725'
    cropBtn.title = 'Toggle crop mode, then drag the photo to reposition it inside the frame'
    cropBtn.style.cssText = 'position:absolute;top:-10px;left:-10px;width:22px;height:22px;border-radius:50%;background:#00c8ff;color:#000;border:2px solid #fff;cursor:pointer;font-size:11px;line-height:1;padding:0;z-index:3;'
    cropBtn.onclick = (e) => {
      e.stopPropagation()
      panMode = !panMode
      cropBtn.style.background = panMode ? '#39ff6a' : '#00c8ff'
      img.style.cursor = panMode ? 'move' : 'grab'
      wrap.style.outline = panMode ? '2px dashed #39ff6a' : 'none'
    }
    wrap.appendChild(cropBtn)

    const handle = document.createElement('div')
    handle.title = 'Drag to resize'
    handle.style.cssText = 'position:absolute;bottom:-6px;right:-6px;width:16px;height:16px;border-radius:3px;background:#f9f9f9;border:2px solid #000;cursor:nwse-resize;z-index:3;'
    wrap.appendChild(handle)

    let mode = null
    let start = null
    let current = { x: photo.x, y: photo.y, w, h, ox, oy }

    wrap.onpointerdown = (e) => {
      if (e.target === handle) mode = 'resize'
      else if (e.target === img && panMode) mode = 'pan'
      else if (e.target === img) mode = 'move'
      else return

      e.preventDefault()
      try {
        wrap.setPointerCapture(e.pointerId)
      } catch (err) {
        // ignore: some pointer types don't support capture, drag still works via bubbling
      }
      start = { clientX: e.clientX, clientY: e.clientY }
      current = { x: photo.x, y: photo.y, w, h, ox, oy }
    }

    wrap.onpointermove = (e) => {
      if (!mode) return
      const dx = e.clientX - start.clientX
      const dy = e.clientY - start.clientY

      if (mode === 'move') {
        current.x = (e.clientX / window.innerWidth) * 100
        current.y = (e.clientY / window.innerHeight) * 100
        wrap.style.left = current.x + '%'
        wrap.style.top = current.y + '%'
      } else if (mode === 'resize') {
        current.w = Math.max(60, w + dx)
        current.h = Math.max(60, h + dy)
        wrap.style.width = current.w + 'px'
        wrap.style.height = current.h + 'px'
      } else if (mode === 'pan') {
        current.ox = Math.min(100, Math.max(0, ox - dx / 2))
        current.oy = Math.min(100, Math.max(0, oy - dy / 2))
        img.style.objectPosition = `${current.ox}% ${current.oy}%`
      }
    }

    const endDrag = () => {
      if (!mode) return
      const finished = mode
      mode = null
      if (finished === 'move') setTriggerValue('moved', { id: photo.id, x: current.x, y: current.y })
      if (finished === 'resize') setTriggerValue('resized', { id: photo.id, w: current.w, h: current.h })
      if (finished === 'pan') setTriggerValue('panned', { id: photo.id, ox: current.ox, oy: current.oy })
    }
    wrap.onpointerup = endDrag
    wrap.onpointercancel = endDrag

    root.appendChild(wrap)
  })

  return () => {
    root.remove()
  }
}
"""

_photo_board = st.components.v2.component(
    "photo_board",
    html="<div></div>",
    js=_PHOTO_BOARD_JS,
)


def render_photo_board(pins: list[dict]) -> None:
    photos = []
    for p in pins:
        uri = _photo_data_uri(p["photo_path"])
        if uri:
            photos.append(
                {
                    "id": p["id"],
                    "src": uri,
                    "x": p["x"],
                    "y": p["y"],
                    "w": p.get("w", 140),
                    "h": p.get("h", 140),
                    "ox": p.get("ox", 50),
                    "oy": p.get("oy", 50),
                }
            )

    owner = is_owner()
    result = _photo_board(
        data={"photos": photos, "is_owner": owner},
        key="photo_board",
        height=2,
        on_moved_change=lambda: None,
        on_resized_change=lambda: None,
        on_panned_change=lambda: None,
        on_deleted_change=lambda: None,
    )
    # The JS only lets an owner trigger these, but enforce it here too —
    # a trigger fired via devtools shouldn't be able to write without the password.
    if owner and result.moved:
        data_store.update_photo_pin(result.moved["id"], x=result.moved["x"], y=result.moved["y"])
        st.rerun()
    if owner and result.resized:
        data_store.update_photo_pin(result.resized["id"], w=result.resized["w"], h=result.resized["h"])
        st.rerun()
    if owner and result.panned:
        data_store.update_photo_pin(result.panned["id"], ox=result.panned["ox"], oy=result.panned["oy"])
        st.rerun()
    if owner and result.deleted:
        data_store.delete_photo_pin(result.deleted)
        st.rerun()


def render_photo_upload() -> None:
    render_owner_gate()
    if not is_owner():
        return
    uploaded = st.file_uploader("Add a photo to the board", type=["jpg", "jpeg", "png"], key="board_uploader")
    if uploaded is not None and st.session_state.get("_last_board_upload") != uploaded.file_id:
        data_store.add_photo_pin(uploaded)
        st.session_state["_last_board_upload"] = uploaded.file_id
        st.rerun()


def main() -> None:
    days = get_days()
    day_info = data_store.load_day_info()
    all_stops = data_store.load_stops()
    photo_pins = data_store.load_photo_pins()

    m = build_map(days, day_info, all_stops)
    st_folium(m, width=None, height=MAP_HEIGHT, returned_objects=[], key="trip_map")
    render_photo_board(photo_pins)

    with st.container(key="board_upload_container"):
        render_photo_upload()


if __name__ == "__main__":
    main()
