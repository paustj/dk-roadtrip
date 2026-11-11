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
    st.session_state.pop("_viewer", None)
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

def _photo_data_uri(path: Path | str) -> str | None:
    full_path = Path(__file__).resolve().parent / path
    if not full_path.exists():
        return None
    b64 = base64.b64encode(full_path.read_bytes()).decode("ascii")
    ext = full_path.suffix.lstrip(".").lower().replace("jpg", "jpeg") or "jpeg"
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
        n_photos = data_store.count_day_photos(day)
        if n_photos:
            meta.append(f"{n_photos} photo{'s' if n_photos > 1 else ''}")
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

    render_gallery(day)

    stops = all_stops.get(day, [])
    if stops:
        st.markdown('<div class="section-label">Stops</div>', unsafe_allow_html=True)
        for s in stops:
            st.markdown(
                f'<div class="dayrow"><span class="num" style="font-size:16px">◆</span>'
                f'<div><div class="t">{html.escape(s.get("name", ""))}</div>'
                f'<div class="m">{html.escape(s.get("category", ""))}</div></div><div></div></div>',
                unsafe_allow_html=True,
            )


def _close_viewer() -> None:
    st.session_state.pop("_viewer", None)


@st.dialog(" ", width="large", on_dismiss=_close_viewer)
def photo_viewer(day: int, photo_id: str) -> None:
    photos = data_store.list_day_photos(day)
    ids = [p["id"] for p in photos]
    if photo_id not in ids:
        st.rerun()
    i = ids.index(photo_id)
    html_block(f'<div class="kicker">Day {day:02d} · photo {i + 1} / {len(photos)}</div>')
    st.image(str(photos[i]["path"]))

    c1, c2, c3 = st.columns([1, 1, 1])
    if c1.button("‹ Prev", key="pv_prev", disabled=i == 0, width="stretch"):
        st.session_state["_viewer"] = (day, ids[i - 1])
        st.rerun()
    if c3.button("Next ›", key="pv_next", disabled=i == len(ids) - 1, width="stretch"):
        st.session_state["_viewer"] = (day, ids[i + 1])
        st.rerun()
    if is_owner() and c2.button("Delete", key="pv_del", width="stretch"):
        data_store.delete_day_photo(day, photo_id)
        st.session_state.pop("_viewer", None)
        st.rerun()


def render_gallery(day: int) -> None:
    photos = data_store.list_day_photos(day)
    label = f"Photos · {len(photos)}" if photos else "Photos"
    st.markdown(f'<div class="section-label">{label}</div>', unsafe_allow_html=True)

    if not photos:
        st.markdown('<div class="empty">NO PHOTOS YET</div>', unsafe_allow_html=True)
    for row in range(0, len(photos), 3):
        cols = st.columns(3, gap="small")
        for col, p in zip(cols, photos[row:row + 3]):
            with col, st.container(key=f"thumb_{day}_{p['id']}"):
                st.markdown(f'<img class="thumb" src="{_photo_data_uri(p["thumb"])}">', unsafe_allow_html=True)
                if st.button("Open", key=f"open_photo_{p['id']}"):
                    st.session_state["_viewer"] = (day, p["id"])
                    st.rerun()

    if is_owner():
        # a fresh key after each upload empties the uploader
        n = st.session_state.get("_upload_n", 0)
        files = st.file_uploader(
            "Add photos", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True,
            key=f"upload_{day}_{n}", label_visibility="collapsed",
        )
        if files:
            with st.spinner("Saving photos…"):
                for f in files:
                    data_store.add_day_photo(day, f)
            st.session_state["_upload_n"] = n + 1
            st.rerun()

    # the viewer is opened from session state so Prev/Next can reopen it after a rerun
    viewer = st.session_state.get("_viewer")
    if viewer and viewer[0] == day:
        photo_viewer(*viewer)


def is_owner() -> bool:
    return bool(st.session_state.get("is_owner"))


def render_owner_panel() -> None:
    st.markdown('<div class="section-label">Admin</div>', unsafe_allow_html=True)
    with st.expander("Owner access", expanded=False):
        if is_owner():
            st.caption("Editing unlocked. Open a day to add or delete photos.")
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


# ---------- page ----------

def main() -> None:
    days = get_days()
    day_info = data_store.load_day_info()
    all_stops = data_store.load_stops()

    with st.sidebar:
        sel = selected_day()
        render_brand(days, day_info, with_stats=sel is None)
        if sel is None:
            render_day_list(days, day_info)
        else:
            render_day_detail(sel, days, day_info, all_stops)
        render_owner_panel()

    render_map(days, day_info)


if __name__ == "__main__":
    main()
