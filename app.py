import base64
import html
import sys
from math import sqrt
from pathlib import Path

import folium
import streamlit as st
from branca.element import MacroElement
from jinja2 import Template
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import data_store  # noqa: E402
import theme as T  # noqa: E402
from gpx_utils import DayRoute, load_all_days  # noqa: E402

st.set_page_config(
    page_title="Denmark Roadtrip '26",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.html(T.APP_CSS)


def html_block(markup: str) -> None:
    # markdown treats indented or blank lines as code / block breaks, so flatten first
    st.markdown("".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True)

# The gap between a day's segments is drawn as a dashed ferry line.
FERRY_CROSSINGS: list[dict] = [
    {"day": 1, "after_segment": 0, "label": "Ferry: Aarhus → Sjællands Odde"},
    {"day": 2, "after_segment": 0, "label": "Ferry: Rørvig → Hundested"},
    {"day": 10, "after_segment": 0, "label": "Ferry crossing (Langelandsbælt)"},
]
DK_CENTER = (56.0, 10.5)



# ---------- data ----------

@st.cache_data
def get_days() -> dict[int, DayRoute]:
    return load_all_days()


def secret(name: str) -> str:
    # st.secrets throws if there's no secrets file at all, e.g. a fresh local clone
    try:
        return st.secrets.get(name, "")
    except Exception:
        return ""


def basemap() -> tuple[str, dict]:
    key = secret("carto_api_key")
    if key:
        cfg = dict(T.BASEMAPS["carto"])
        cfg["url"] = cfg["url"].replace("{key}", key)
        return "carto", cfg
    return "esri", T.BASEMAPS["esri"]


def selected_day() -> int | None:
    return st.session_state.get("day")


def select_day(day: int | None) -> None:
    st.session_state["day"] = day
    # drop old map widget state so a stale click can't re-select a day
    for k in [k for k in st.session_state if str(k).startswith("trip_map_")]:
        del st.session_state[k]
    st.session_state.pop("_tip_seen", None)


def ferries_on(day: int) -> list[dict]:
    return [c for c in FERRY_CROSSINGS if c["day"] == day]


def day_anchor(day: int, days: dict[int, DayRoute]) -> tuple[float, float]:
    """Where a day 'happens'. Rest days borrow the previous day's end point."""
    for d in range(day, 0, -1):
        if days[d].has_route:
            return days[d].segments[-1][-1]
    return DK_CENTER


# ---------- map ----------

class MapHud(MacroElement):
    """Adds grid, rulers, coordinate readout and the title lockup on top of the map."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        (function () {
          var map = {{ this._parent.get_name() }};
          var box = map.getContainer();
          box.insertAdjacentHTML('beforeend', {{ this.overlay_html }});

          // rulers: numbers across the top, letters down the side, one per 120px grid cell
          function rulers() {
            var top = box.querySelector('.hud-ruler.top'), left = box.querySelector('.hud-ruler.left');
            top.innerHTML = ''; left.innerHTML = '';
            for (var x = 120, i = 1; x < box.clientWidth; x += 120, i++)
              top.insertAdjacentHTML('beforeend', '<span style="left:' + (x - 4) + 'px">' + i + '</span>');
            for (var y = 120, j = 0; y < box.clientHeight; y += 120, j++)
              left.insertAdjacentHTML('beforeend', '<span style="top:' + (y - 6) + 'px">' + String.fromCharCode(65 + j) + '</span>');
          }
          rulers();
          window.addEventListener('resize', rulers);

          var out = box.querySelector('.hud-readout');
          function readout(ll) {
            out.innerHTML = 'LAT <b>' + ll.lat.toFixed(4) + '°N</b> / LON <b>' + ll.lng.toFixed(4) +
              '°E</b> · Z <b>' + map.getZoom().toFixed(1) + '</b>';
          }
          readout(map.getCenter());
          map.on('mousemove', function (e) { readout(e.latlng); });
          map.on('zoomend moveend', function () { readout(map.getCenter()); });
        })();
        {% endmacro %}
        """
    )

    def __init__(self, overlay_html: str):
        super().__init__()
        self._name = "MapHud"
        # passed to JS as a string literal
        self.overlay_html = "`" + overlay_html.replace("`", "'").replace("\n", " ") + "`"


def lockup_html(day: int | None, day_info: dict[int, data_store.DayInfo], total_km: float) -> str:
    if day is None:
        dates = [i.date for i in day_info.values() if i.date]
        span = f"{min(dates):%d.%m} – {max(dates):%d.%m.%Y}" if dates else ""
        kicker, big, sub = "Roadtrip '26", "Denmark", f"{total_km:,.0f} km · {span}"
    else:
        info = day_info[day]
        kicker = f"Day {day:02d} / {len(day_info):02d}"
        big = info.place_to if info.place_to != info.place_from else info.place_from
        sub = f"from {info.place_from}" if info.place_to != info.place_from else (info.note or "")
    return (
        f'<div class="hud-lockup"><div class="kicker">{html.escape(kicker)}</div>'
        f'<div class="big">{html.escape(big)}</div><div class="sub">{html.escape(sub)}</div></div>'
    )


def build_map(days: dict[int, DayRoute], day_info: dict[int, data_store.DayInfo], sel: int | None) -> folium.Map:
    name, bm = basemap()
    m = folium.Map(
        location=DK_CENTER,
        zoom_start=8,
        min_zoom=6,
        max_zoom=bm["max_zoom"],
        zoomSnap=0.25,
        tiles=None,
        zoom_control=False,
        prefer_canvas=False,
    )
    folium.TileLayer(bm["url"], attr=bm["attr"], name=name, max_zoom=bm["max_zoom"]).add_to(m)

    root = m.get_root()
    root.header.add_child(folium.Element(f'<link rel="stylesheet" href="{T.FONTS_URL}">'))
    root.header.add_child(folium.Element(T.MAP_CSS))
    root.html.add_child(folium.Element(T.tile_filter_svg(bm["dark"], bm["light"])))

    max_km = max(d.distance_km for d in days.values()) or 1

    for day, route in days.items():
        if not route.has_route:
            continue
        info = day_info[day]
        active = sel is None or sel == day
        tip = f"Day {day} · {info.title}"
        color = T.AMBER if active else T.BLUE

        for segment in route.segments:
            if active:
                # soft glow underneath
                folium.PolyLine(segment, color=T.AMBER, weight=12, opacity=0.12).add_to(m)
            folium.PolyLine(
                segment,
                color=color,
                weight=4.5 if sel == day else 3,
                opacity=1 if active else 0.35,
                tooltip=tip,
            ).add_to(m)

        for crossing in ferries_on(day):
            i = crossing["after_segment"]
            if i + 1 >= len(route.segments):
                continue
            gap = [route.segments[i][-1], route.segments[i + 1][0]]
            folium.PolyLine(
                gap, color=color, weight=2, opacity=0.9 if active else 0.35, dash_array="2, 8",
                tooltip=f"⛴ {crossing['label']}",
            ).add_to(m)

        # overnight marker at the end of the day, sized by distance driven
        size = 8 + 12 * sqrt(route.distance_km / max_km)
        dim = "" if active else " dim"
        icon = folium.DivIcon(
            html=(
                f'<div class="dm{dim}"><span class="dot" style="width:{size:.0f}px;height:{size:.0f}px"></span>'
                f'<span class="lbl" style="left:{size / 2 + 6:.0f}px"><u>{day:02d}</u>'
                f"<small>{html.escape(info.place_to.upper())} · {route.distance_km:.0f} KM</small></span></div>"
            ),
            icon_size=(0, 0),
            icon_anchor=(0, 0),
        )
        folium.Marker(route.segments[-1][-1], icon=icon, tooltip=tip).add_to(m)

    # frame the selection
    if sel is not None and days[sel].has_route:
        pts = days[sel].all_points
        m.fit_bounds(
            [[min(p[0] for p in pts), min(p[1] for p in pts)], [max(p[0] for p in pts), max(p[1] for p in pts)]],
            padding_top_left=(60, 140), padding_bottom_right=(60, 60),
        )
    elif sel is not None:
        m.location = list(day_anchor(sel, days))
        m.options["zoom"] = 12
    else:
        pts = [p for d in days.values() for p in d.all_points]
        m.fit_bounds(
            [[min(p[0] for p in pts), min(p[1] for p in pts)], [max(p[0] for p in pts), max(p[1] for p in pts)]],
            padding_top_left=(40, 150), padding_bottom_right=(40, 40),
        )

    total_km = sum(d.distance_km for d in days.values())
    overlay = (
        '<div class="hud-grid"></div><div class="hud-ruler top"></div><div class="hud-ruler left"></div>'
        + lockup_html(sel, day_info, total_km)
        + '<div class="hud-readout"></div>'
    )
    m.add_child(MapHud(overlay))
    return m


def render_map(days, day_info) -> None:
    sel = selected_day()
    result = st_folium(
        build_map(days, day_info, sel),
        width=None,
        height=900,
        returned_objects=["last_object_clicked_tooltip"],
        key=f"trip_map_{sel}",
    )
    # clicking a route or marker selects that day
    tip = (result or {}).get("last_object_clicked_tooltip") or ""
    token = f"{sel}|{tip}"
    if tip.startswith("Day ") and token != st.session_state.get("_tip_seen"):
        st.session_state["_tip_seen"] = token
        try:
            day = int(tip.split()[1])
        except ValueError:
            return
        if day != sel:
            select_day(day)
            st.rerun()


# ---------- sidebar ----------

def _photo_data_uri(relative_path: str) -> str | None:
    full_path = Path(__file__).resolve().parent / relative_path
    if not full_path.exists():
        return None
    b64 = base64.b64encode(full_path.read_bytes()).decode("ascii")
    ext = full_path.suffix.lstrip(".").lower() or "jpeg"
    return f"data:image/{ext};base64,{b64}"


def render_brand(days, day_info, with_stats: bool = True) -> None:
    total_km = sum(d.distance_km for d in days.values())
    dates = [i.date for i in day_info.values() if i.date]
    span = f"{min(dates):%d.%m} – {max(dates):%d.%m.%Y}" if dates else ""
    html_block(
        f"""
        <div class="brand">
          <div class="kicker">{span}</div>
          <div class="t1">DK Roadtrip '26</div>
          <div class="t2">Field Log</div>
        </div>
        """
    )
    if with_stats:
        html_block(
            f"""
            <div class="stats">
              <div><b>{total_km:,.0f}</b><span>KM DRIVEN</span></div>
              <div><b>{len(days)}</b><span>DAYS</span></div>
              <div><b>{len(FERRY_CROSSINGS)}</b><span>FERRIES</span></div>
            </div>
            """
        )


def render_day_list(days, day_info) -> None:
    st.markdown('<div class="section-label">Daily log</div>', unsafe_allow_html=True)
    max_km = max(d.distance_km for d in days.values()) or 1
    for day, route in days.items():
        info = day_info[day]
        meta = [info.date.strftime("%a %d %b") if info.date else ""]
        if ferries_on(day):
            meta.append("ferry")
        if info.note:
            meta.append(info.note)
        km = f"{route.distance_km:.0f}<small>KM</small>" if route.has_route else "—<small>REST</small>"
        bar = (
            f'<div class="bar" style="width:{120 * route.distance_km / max_km:.0f}px"></div>'
            if route.has_route else ""
        )
        with st.container(key=f"dayrow_{day}"):
            html_block(
                f"""<div class="dayrow{'' if route.has_route else ' rest'}">
                  <span class="num">{day:02d}</span>
                  <div><div class="t">{html.escape(info.title)}</div>
                  <div class="m">{html.escape(' · '.join(m for m in meta if m))}</div></div>
                  <div class="km">{km}</div>{bar}</div>"""
            )
            if st.button(f"Open day {day}", key=f"open_{day}"):
                select_day(day)
                st.rerun()


def render_day_detail(day: int, days, day_info, all_stops) -> None:
    info = day_info[day]
    route = days[day]
    last = max(days)

    c1, c2, c3 = st.columns(3)
    if c1.button("‹ Prev", key="prev", disabled=day <= 1, width="stretch"):
        select_day(day - 1)
        st.rerun()
    if c2.button("All", key="all", width="stretch"):
        select_day(None)
        st.rerun()
    if c3.button("Next ›", key="next", disabled=day >= last, width="stretch"):
        select_day(day + 1)
        st.rerun()

    note = f'<div class="note">{html.escape(info.note)}</div>' if info.note else ""
    html_block(
        f"""
        <div class="detail" style="margin-top:20px">
          <div class="kicker">{info.date_label}</div>
          <div class="daynum">{day:02d}<small>/ {last:02d}</small></div>
          <div class="route">{html.escape(info.title)}</div>
          {note}
        </div>
        """
    )

    if route.has_route:
        html_block(
            f"""
            <div class="stats">
              <div><b>{route.distance_km:.0f}</b><span>KM</span></div>
              <div><b>{len(route.segments)}</b><span>LEGS</span></div>
              <div><b>{len(ferries_on(day))}</b><span>FERRIES</span></div>
            </div>
            """
        )

    st.markdown('<div class="section-label">Journal</div>', unsafe_allow_html=True)
    story = data_store.load_journal_text(day)
    if story:
        st.markdown(f'<div class="story">{html.escape(story).replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="empty">NO ENTRY YET</div>', unsafe_allow_html=True)

    stops = all_stops.get(day, [])
    photos = [s for s in stops if s.get("photo_path") and (Path(__file__).parent / s["photo_path"]).exists()]
    if stops:
        st.markdown('<div class="section-label">Stops</div>', unsafe_allow_html=True)
        for s in stops:
            st.markdown(
                f'<div class="dayrow"><span class="num" style="font-size:16px">◆</span>'
                f'<div><div class="t">{html.escape(s.get("name", ""))}</div>'
                f'<div class="m">{html.escape(s.get("category", ""))}</div></div><div></div></div>',
                unsafe_allow_html=True,
            )
    if photos:
        cols = st.columns(2)
        for i, s in enumerate(photos):
            cols[i % 2].image(str(Path(__file__).parent / s["photo_path"]), width="stretch")


def is_owner() -> bool:
    return bool(st.session_state.get("is_owner"))


def render_owner_panel() -> None:
    st.markdown('<div class="section-label">Admin</div>', unsafe_allow_html=True)
    with st.expander("Owner access", expanded=False):
        if is_owner():
            st.caption("Editing unlocked")
            uploaded = st.file_uploader("Pin a photo on the map", type=["jpg", "jpeg", "png"], key="board_uploader")
            if uploaded is not None and st.session_state.get("_last_board_upload") != uploaded.file_id:
                data_store.add_photo_pin(uploaded)
                st.session_state["_last_board_upload"] = uploaded.file_id
                st.rerun()
            if st.button("Lock", key="lock_btn", width="stretch"):
                st.session_state["is_owner"] = False
                st.rerun()
            return

        pw = st.text_input("Password", type="password", key="owner_pw", label_visibility="collapsed",
                           placeholder="Password to edit")
        if st.button("Unlock editing", key="unlock_btn", width="stretch"):
            expected = secret("board_password")
            if expected and pw == expected:
                st.session_state["is_owner"] = True
                st.rerun()
            else:
                st.error("Wrong password.")


# ---------- photo board (free photos pinned over the map) ----------

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
  const c = (data && data.colors) || {}

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
      border:2px solid ${c.amber};outline:1px solid ${c.navy};outline-offset:3px;
      box-shadow:0 0 0 4px ${c.navy}, 0 0 0 5px ${c.line}, 0 10px 30px rgba(0,0,0,.6);display:block;cursor:grab;`
    wrap.appendChild(img)

    if (!isOwner) {
      root.appendChild(wrap)
      return
    }

    const btn = (txt, title, css) => {
      const b = document.createElement('button')
      b.textContent = txt
      b.title = title
      b.style.cssText = `position:absolute;width:22px;height:22px;border:1px solid ${c.amber};background:${c.navy};
        color:${c.amber};cursor:pointer;font:500 12px monospace;line-height:1;padding:0;z-index:3;` + css
      return b
    }

    const delBtn = btn('\\u00d7', 'Delete', 'top:-11px;right:-11px;')
    delBtn.onclick = (e) => {
      e.stopPropagation()
      setTriggerValue('deleted', photo.id)
    }
    wrap.appendChild(delBtn)

    let panMode = false
    const cropBtn = btn('\\u2725', 'Toggle crop mode, then drag the photo to reposition it inside the frame', 'top:-11px;left:-11px;')
    cropBtn.onclick = (e) => {
      e.stopPropagation()
      panMode = !panMode
      cropBtn.style.background = panMode ? c.amber : c.navy
      cropBtn.style.color = panMode ? c.navy : c.amber
      img.style.cursor = panMode ? 'move' : 'grab'
    }
    wrap.appendChild(cropBtn)

    const handle = document.createElement('div')
    handle.title = 'Drag to resize'
    handle.style.cssText = `position:absolute;bottom:-7px;right:-7px;width:14px;height:14px;background:${c.amber};
      border:2px solid ${c.navy};cursor:nwse-resize;z-index:3;`
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
        // some pointer types can't be captured; dragging still works
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

_photo_board = st.components.v2.component("photo_board", html="<div></div>", js=_PHOTO_BOARD_JS)


def render_photo_board(pins: list[dict]) -> None:
    photos = []
    for p in pins:
        uri = _photo_data_uri(p["photo_path"])
        if uri:
            photos.append({
                "id": p["id"], "src": uri, "x": p["x"], "y": p["y"],
                "w": p.get("w", 140), "h": p.get("h", 140),
                "ox": p.get("ox", 50), "oy": p.get("oy", 50),
            })

    owner = is_owner()
    result = _photo_board(
        data={
            "photos": photos,
            "is_owner": owner,
            "colors": {"amber": T.AMBER, "navy": T.NAVY_950, "line": T.LINE},
        },
        key="photo_board",
        height=2,
        on_moved_change=lambda: None,
        on_resized_change=lambda: None,
        on_panned_change=lambda: None,
        on_deleted_change=lambda: None,
    )
    # the JS only lets an owner fire these, but check here too so devtools can't write without the password
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


# ---------- page ----------

def main() -> None:
    days = get_days()
    day_info = data_store.load_day_info()
    all_stops = data_store.load_stops()
    photo_pins = data_store.load_photo_pins()

    with st.sidebar:
        sel = selected_day()
        render_brand(days, day_info, with_stats=sel is None)
        if sel is None:
            render_day_list(days, day_info)
        else:
            render_day_detail(sel, days, day_info, all_stops)
        render_owner_panel()

    render_map(days, day_info)
    render_photo_board(photo_pins)


if __name__ == "__main__":
    main()
