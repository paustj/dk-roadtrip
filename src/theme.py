"""Colours, fonts and CSS for the blueprint look. Tweak the look here, not in app.py."""

# Palette: deep navy base, electric blue linework, amber for the trip itself.
NAVY_950 = "#050c1f"
NAVY_900 = "#081530"
NAVY_800 = "#0c1d42"
NAVY_700 = "#12295a"
LINE = "#1f3d7a"
BLUE = "#4d8dff"
BLUE_LIGHT = "#9cc2ff"
AMBER = "#ffb000"
AMBER_DIM = "#a8770a"
TEXT = "#dbe7ff"
MUTED = "#7f9cd1"
DANGER = "#ff5a5f"

FONTS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Barlow+Condensed:ital,wght@0,300;0,500;0,600;1,600;1,700;1,800"
    "&family=Barlow:wght@400;500;600"
    "&family=JetBrains+Mono:wght@400;500"
    "&display=swap"
)

# Basemaps. Esri is the default since it needs no key. CARTO is used if
# carto_api_key is set in secrets (free key at carto.com/basemaps/apikey).
BASEMAPS = {
    "esri": {
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        "attr": "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors",
        "max_zoom": 16,
        # Measured grey levels of the tiles: water ~0.14, land ~0.28.
        "dark": 0.14,
        "light": 0.28,
    },
    "carto": {
        "url": "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png?key={key}",
        "attr": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
        '&copy; <a href="https://carto.com/attributions">CARTO</a>',
        "max_zoom": 19,
        # Not measured yet. If the map looks too dark or bright with CARTO, nudge these.
        "dark": 0.03,
        "light": 0.18,
    },
}

# What the two grey levels above get mapped to (sea and land), as 0-1 RGB.
SEA_RGB = (0.031, 0.082, 0.188)   # ~#081530
LAND_RGB = (0.071, 0.161, 0.353)  # ~#12295a
# Edge glow colour multipliers. Higher = brighter coastlines and roads.
EDGE_GAIN = (1.4, 3.0, 5.2)  # tuned on real Esri tiles


def tile_filter_svg(dark: float, light: float) -> str:
    """SVG filter that recolours grey tiles to navy and adds a blue glow on edges.

    Step 1 turns the tile into luminance. Step 2 maps luminance linearly so
    `dark` lands on SEA_RGB and `light` on LAND_RGB. Step 3 finds edges
    (dilate minus original) and adds them back in electric blue.
    """
    span = light - dark
    g = round(dark * 255)  # fill gaps between tiles with sea colour so they don't read as edges
    funcs = []
    for ch, sea, land in zip("RGB", SEA_RGB, LAND_RGB):
        slope = (land - sea) / span
        intercept = sea - slope * dark
        funcs.append(f'<feFunc{ch} type="linear" slope="{slope:.4f}" intercept="{intercept:.4f}"/>')
    edge = "".join(
        f'<feFunc{ch} type="linear" slope="{g}" intercept="0"/>' for ch, g in zip("RGB", EDGE_GAIN)
    )
    # grown - lum written as grown + (1 - lum) - 1, so alpha stays 1 (a plain subtract zeroes alpha)
    inv = "".join(f'<feFunc{ch} type="linear" slope="-1" intercept="1"/>' for ch in "RGB")
    return f"""
    <svg width="0" height="0" style="position:absolute" aria-hidden="true">
      <filter id="blueprint" color-interpolation-filters="sRGB" x="0" y="0" width="100%" height="100%">
        <feFlood flood-color="rgb({g},{g},{g})" result="bg"/>
        <feComposite in="SourceGraphic" in2="bg" operator="over" result="flat"/>
        <feColorMatrix in="flat" type="matrix" result="lum"
          values="0.299 0.587 0.114 0 0  0.299 0.587 0.114 0 0  0.299 0.587 0.114 0 0  0 0 0 1 0"/>
        <feComponentTransfer in="lum" result="base">{''.join(funcs)}</feComponentTransfer>
        <feMorphology in="lum" operator="dilate" radius="1" result="grown"/>
        <feComponentTransfer in="lum" result="inv">{inv}</feComponentTransfer>
        <feComposite in="grown" in2="inv" operator="arithmetic" k1="0" k2="1" k3="1" k4="-1" result="edgeRaw"/>
        <feComponentTransfer in="edgeRaw" result="edge">{edge}</feComponentTransfer>
        <feComposite in="edge" in2="base" operator="arithmetic" k1="0" k2="1" k3="1" k4="0"/>
      </filter>
    </svg>
    """


# CSS that lives inside the folium map iframe.
MAP_CSS = f"""
<style>
html, body {{ background:{NAVY_900}; height:100%; margin:0; overflow:hidden; }}
#map_div, .folium-map {{ height:100vh !important; }}
.leaflet-container {{ background:{NAVY_900} !important; font-family:'Barlow',sans-serif; }}
.leaflet-tile-pane {{ filter:url(#blueprint); }}

/* blueprint grid: fine dots, major lines every 120px, + marks on intersections */
.hud-grid {{
  position:absolute; inset:0; z-index:450; pointer-events:none;
  background-image:
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cpath d='M54 60h12M60 54v12' stroke='%239cc2ff' stroke-opacity='.55' stroke-width='1'/%3E%3C/svg%3E"),
    radial-gradient(circle, rgba(156,194,255,.22) 0.8px, transparent 1.2px),
    repeating-linear-gradient(0deg, transparent 0 119px, rgba(77,141,255,.13) 119px 120px),
    repeating-linear-gradient(90deg, transparent 0 119px, rgba(77,141,255,.13) 119px 120px);
  background-size:120px 120px, 24px 24px, 120px 120px, 120px 120px;
  background-position:-60px -60px, 0 0, 0 0, 0 0;
}}
.hud-ruler {{ position:absolute; z-index:460; pointer-events:none; font:500 10px 'JetBrains Mono',monospace;
  color:{MUTED}; letter-spacing:1px; }}
.hud-ruler span {{ position:absolute; }}
.hud-ruler.top {{ top:6px; left:0; right:0; height:14px; }}
.hud-ruler.left {{ top:0; bottom:0; left:8px; width:14px; }}

.hud-lockup {{ position:absolute; top:64px; right:40px; z-index:470; text-align:right; pointer-events:none; }}
.hud-lockup .kicker {{ font:300 22px/1 'Barlow Condensed',sans-serif; letter-spacing:4px; color:{BLUE_LIGHT};
  text-transform:uppercase; }}
.hud-lockup .big {{ font:italic 800 64px/0.95 'Barlow Condensed',sans-serif; color:{AMBER};
  text-transform:uppercase; letter-spacing:-0.5px; margin-top:4px; }}
.hud-lockup .sub {{ font:300 20px/1.1 'Barlow Condensed',sans-serif; letter-spacing:4px; color:{BLUE_LIGHT};
  text-transform:uppercase; margin-top:6px; }}

.hud-readout {{ position:absolute; left:30px; bottom:18px; z-index:470; pointer-events:none;
  font:400 11px 'JetBrains Mono',monospace; color:{MUTED}; letter-spacing:1px; }}
.hud-readout b {{ color:{BLUE_LIGHT}; font-weight:500; }}

/* day markers */
.dm {{ position:relative; width:0; height:0; }}
.dm .dot {{ position:absolute; transform:translate(-50%,-50%); border-radius:50%; background:{AMBER};
  box-shadow:0 0 0 3px rgba(255,176,0,.18), 0 0 14px rgba(255,176,0,.55); }}
.dm .lbl {{ position:absolute; left:10px; top:-7px; white-space:nowrap; font:500 12px 'JetBrains Mono',monospace;
  color:{AMBER}; text-shadow:0 0 6px {NAVY_900}, 0 0 2px {NAVY_900}; }}
.dm .lbl u {{ text-underline-offset:3px; }}
.dm .lbl small {{ display:block; font:400 9.5px 'JetBrains Mono',monospace; color:{BLUE_LIGHT};
  letter-spacing:1px; text-decoration:none; margin-top:1px; }}
.dm.dim .dot {{ background:{BLUE}; box-shadow:none; opacity:.5; }}
.dm.dim .lbl {{ color:{MUTED}; opacity:.6; }}
.dm.dim .lbl small {{ display:none; }}

.leaflet-tooltip {{ background:{NAVY_950}; color:{TEXT}; border:1px solid {AMBER}; border-radius:0;
  font:500 12px 'JetBrains Mono',monospace; box-shadow:none; padding:4px 8px; }}
.leaflet-tooltip:before {{ display:none; }}
.leaflet-control-attribution {{ background:rgba(5,12,31,.7) !important; color:{MUTED} !important;
  font:400 9px 'JetBrains Mono',monospace; }}
.leaflet-control-attribution a {{ color:{BLUE_LIGHT} !important; }}
.leaflet-control-zoom a {{ background:{NAVY_950} !important; color:{BLUE_LIGHT} !important;
  border:1px solid {LINE} !important; border-radius:0 !important; }}
.leaflet-bar {{ border:none !important; box-shadow:none !important; }}

@media (max-width: 900px) {{
  .hud-lockup .big {{ font-size:40px; }}
  .hud-lockup .kicker, .hud-lockup .sub {{ font-size:15px; letter-spacing:3px; }}
}}
</style>
"""


# CSS for the Streamlit page around the map.
APP_CSS = f"""
<style>
@import url("{FONTS_URL}");
/* map fills the main area */
div.block-container {{ padding:0 !important; max-width:100% !important; }}
section[data-testid="stMain"] {{ background:{NAVY_900}; }}
header[data-testid="stHeader"] {{ background:transparent; }}
iframe {{ display:block; }}
section[data-testid="stMain"] {{ overflow:hidden; }}
iframe[title="streamlit_folium.st_folium"] {{ height:100vh !important; width:100% !important; }}

/* sidebar */
section[data-testid="stSidebar"] {{ background:{NAVY_950}; border-right:1px solid {LINE};
  min-width:360px; }}
section[data-testid="stSidebar"] > div {{
  background-image:
    radial-gradient(circle, rgba(156,194,255,.10) 0.8px, transparent 1.2px);
  background-size:20px 20px;
}}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding-top:1.2rem; }}

.kicker {{ font:400 10.5px 'JetBrains Mono',monospace; letter-spacing:2px; color:{MUTED};
  text-transform:uppercase; }}
.brand .t1 {{ font:300 18px/1 'Barlow Condensed',sans-serif; letter-spacing:5px; color:{BLUE_LIGHT};
  text-transform:uppercase; margin-top:10px; }}
.brand .t2 {{ font:italic 800 46px/0.95 'Barlow Condensed',sans-serif; color:{AMBER};
  text-transform:uppercase; }}

.stats {{ display:grid; grid-template-columns:repeat(3,1fr); border:1px solid {LINE}; margin:18px 0 6px; }}
.brand {{ margin-bottom:16px; }}
.stats div {{ padding:10px 12px; border-right:1px solid {LINE}; }}
.stats div:last-child {{ border-right:none; }}
.stats b {{ display:block; font:italic 700 28px/1 'Barlow Condensed',sans-serif; color:{TEXT}; }}
.stats span {{ font:400 9.5px 'JetBrains Mono',monospace; letter-spacing:2px; color:{MUTED}; }}

.section-label {{ display:flex; align-items:center; gap:10px; margin:22px 0 8px;
  font:400 10.5px 'JetBrains Mono',monospace; letter-spacing:2px; color:{MUTED}; text-transform:uppercase; }}
.section-label:after {{ content:""; flex:1; border-top:1px dashed {LINE}; }}

/* day rows: an html card with an invisible full-size button on top */
[class*="st-key-dayrow_"] {{ position:relative; gap:0 !important; }}
[class*="st-key-dayrow_"] [data-testid="stElementContainer"]:has([data-testid="stButton"]) {{
  position:absolute; inset:0; z-index:2; margin:0;
}}
[class*="st-key-dayrow_"] [data-testid="stButton"],
[class*="st-key-dayrow_"] [data-testid="stButton"] button {{ width:100%; height:100%; opacity:0; cursor:pointer; }}
.dayrow {{ display:grid; grid-template-columns:38px 1fr auto; align-items:center; gap:10px;
  padding:9px 10px 11px; border:1px solid transparent; border-bottom:1px solid rgba(31,61,122,.6);
  position:relative; transition:background .12s, border-color .12s; }}
[class*="st-key-dayrow_"]:hover .dayrow {{ background:rgba(77,141,255,.08); border-color:{LINE}; }}
.dayrow .num {{ font:italic 700 24px/1 'Barlow Condensed',sans-serif; color:{AMBER}; }}
.dayrow .t {{ font:600 15px/1.2 'Barlow',sans-serif; color:{TEXT}; }}
.dayrow .m {{ font:400 10px 'JetBrains Mono',monospace; letter-spacing:1px; color:{MUTED};
  text-transform:uppercase; margin-top:3px; }}
.dayrow .km {{ font:500 13px 'JetBrains Mono',monospace; color:{BLUE_LIGHT}; text-align:right; }}
.dayrow .km small {{ display:block; font-size:9px; letter-spacing:1px; color:{MUTED}; }}
.dayrow .bar {{ position:absolute; left:58px; bottom:4px; height:2px; background:{AMBER}; opacity:.7; }}
.dayrow.rest .num {{ color:{MUTED}; }}

/* day detail */
.detail .daynum {{ font:italic 800 76px/0.9 'Barlow Condensed',sans-serif; color:{AMBER}; }}
.detail .daynum small {{ font:300 22px 'Barlow Condensed',sans-serif; font-style:normal; letter-spacing:3px;
  color:{BLUE_LIGHT}; margin-left:6px; }}
.detail .route {{ font:italic 700 24px/1.15 'Barlow Condensed',sans-serif; letter-spacing:1px; color:{TEXT};
  text-transform:uppercase; margin-top:8px; }}
.detail .note {{ display:inline-block; margin-top:10px; padding:3px 8px; border:1px solid {AMBER};
  color:{AMBER}; font:500 10.5px 'JetBrains Mono',monospace; letter-spacing:1.5px; text-transform:uppercase; }}
.empty {{ font:400 11px 'JetBrains Mono',monospace; color:{MUTED}; letter-spacing:1px;
  border:1px dashed {LINE}; padding:14px; text-align:center; }}

/* photo gallery: thumbnail with an invisible button on top, same trick as day rows */
[class*="st-key-thumb_"] {{ position:relative; gap:0 !important; }}
[class*="st-key-thumb_"] [data-testid="stElementContainer"]:has([data-testid="stButton"]) {{
  position:absolute; inset:0; z-index:2; margin:0;
}}
[class*="st-key-thumb_"] [data-testid="stButton"],
[class*="st-key-thumb_"] [data-testid="stButton"] button {{ width:100%; height:100%; opacity:0; cursor:zoom-in; }}
img.thumb {{ display:block; width:100%; aspect-ratio:1; object-fit:cover; border:1px solid {LINE};
  transition:border-color .12s, transform .12s; }}
[class*="st-key-thumb_"]:hover img.thumb {{ border-color:{AMBER}; }}
section[data-testid="stSidebar"] [data-testid="stColumn"] {{ min-width:0; }}
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-thumb_"]) {{ gap:6px; margin-bottom:6px; }}

/* photo viewer dialog */
[role="dialog"] {{ background:{NAVY_950}; border:1px solid {LINE}; border-radius:0; }}
[role="dialog"] [data-testid="stElementContainer"]:has([data-testid="stImage"]) {{ align-self:center; }}
[role="dialog"] [data-testid="stImage"] img {{ max-height:72vh !important; max-width:100% !important;
  width:auto !important; height:auto !important; margin:0 auto; display:block; border:1px solid {LINE}; }}
[role="dialog"] [data-testid="stButton"] button {{ background:transparent; border:1px solid {LINE}; border-radius:0;
  color:{BLUE_LIGHT}; font:500 11px 'JetBrains Mono',monospace; letter-spacing:1.5px; text-transform:uppercase; }}
[role="dialog"] [data-testid="stButton"] button:hover {{ border-color:{AMBER}; color:{AMBER}; }}

/* buttons */
section[data-testid="stSidebar"] [data-testid="stButton"] button {{
  background:transparent; border:1px solid {LINE}; border-radius:0; color:{BLUE_LIGHT};
  font:500 11px 'JetBrains Mono',monospace; letter-spacing:1.5px; text-transform:uppercase; min-height:34px;
}}
section[data-testid="stSidebar"] [data-testid="stButton"] button:hover {{ border-color:{AMBER}; color:{AMBER}; }}
section[data-testid="stSidebar"] [data-testid="stButton"] button:disabled {{ opacity:.3; }}
section[data-testid="stSidebar"] [data-testid="stButton"] button p {{ font:inherit; }}

/* owner panel */
section[data-testid="stSidebar"] [data-testid="stExpander"] details {{ border:1px dashed {LINE}; border-radius:0;
  background:transparent; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary p {{ font:400 10.5px 'JetBrains Mono',monospace;
  letter-spacing:2px; color:{MUTED}; text-transform:uppercase; }}
section[data-testid="stSidebar"] input {{ border-radius:0 !important; font-family:'JetBrains Mono',monospace; }}
[data-testid="stFileUploaderDropzone"] {{ background:{NAVY_800}; border:1px dashed {LINE}; border-radius:0; }}
</style>
"""
