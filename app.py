"""
CRC Dynasty Dashboard  — Sleeper Fantasy Football
"""
import hashlib
import json
import random
import uuid
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────
LEAGUE_ID = "1312122172180824064"
BASE_URL   = "https://api.sleeper.app/v1"

st.set_page_config(
    page_title="CRC Dynasty",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
/* ── Base ──────────────────────────────────────────── */
.metric-card{background:#1e1e2e;border-radius:12px;padding:16px 20px;
             border:1px solid #313244;text-align:center;margin-bottom:8px}
.metric-card .label{color:#a6adc8;font-size:.8rem;text-transform:uppercase;letter-spacing:.05em}
.metric-card .value{color:#cdd6f4;font-size:1.6rem;font-weight:700;margin-top:4px}
.metric-card .sub  {color:#6c7086;font-size:.75rem;margin-top:2px}
.champ-banner{background:linear-gradient(135deg,#f9e2af22,#fab38722);
              border:1px solid #f9e2af55;border-radius:12px;padding:16px 24px;margin-bottom:16px}
.sec-hdr{font-size:1.1rem;font-weight:600;color:#cdd6f4;
         border-bottom:2px solid #313244;padding-bottom:6px;margin:20px 0 12px 0}
.ig-row-hdr{background:#181825;border-radius:10px;padding:10px 14px;
            font-weight:700;color:#cdd6f4;font-size:.95rem;margin:8px 0 4px 0;
            border-left:3px solid #89b4fa}
.ig-row-hdr span{font-size:.72rem;font-weight:400;color:#6c7086;margin-left:6px}
.bracket-match{background:#1e1e2e;border:1px solid #313244;border-radius:10px;
               padding:12px 16px;margin:4px 0}
.bracket-winner{color:#a6e3a1;font-weight:700}
.bracket-loser {color:#f38ba888}

/* ── Mobile ─────────────────────────────────────────── */
@media (max-width: 768px) {
  /* Reduce outer padding */
  .main .block-container{padding-left:0.75rem!important;padding-right:0.75rem!important}

  /* Prevent iOS auto-zoom on input focus (must be 16px+) */
  input, textarea, select{font-size:16px!important}

  /* Taller touch targets for text inputs */
  .stTextInput > div > div > input{min-height:44px!important;padding:0 10px!important}

  /* Compact metric cards */
  .metric-card{padding:10px 12px!important}
  .metric-card .value{font-size:1.2rem!important}
  .metric-card .label{font-size:.72rem!important}

  /* Smaller headings */
  h1{font-size:1.4rem!important}
  h2,h3{font-size:1.1rem!important}
  .sec-hdr{font-size:.95rem!important}

  /* Tabs: horizontal scroll, no text wrapping */
  .stTabs [data-baseweb="tab-list"]{overflow-x:auto!important;flex-wrap:nowrap!important;
    -webkit-overflow-scrolling:touch;scrollbar-width:none}
  .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar{display:none}
  .stTabs [data-baseweb="tab"]{white-space:nowrap!important;padding:8px 10px!important}

  /* Champ banner compact */
  .champ-banner{padding:10px 14px!important;font-size:.9rem}

  /* Grid row header compact */
  .ig-row-hdr{font-size:.85rem!important;padding:8px 10px!important}

  /* Bracket cards compact */
  .bracket-match{padding:8px 10px!important}

  /* Buttons full width */
  .stButton > button{width:100%!important}

  /* Form submit button */
  .stFormSubmitButton > button{width:100%!important;min-height:48px!important;
    font-size:1rem!important}

  /* Selectbox and slider larger touch */
  .stSelectbox > div > div{min-height:44px!important}
  .stSlider{padding:0!important}
}
</style>
""", unsafe_allow_html=True)

# ─── API layer ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def api_get(path):
    r = requests.get(f"{BASE_URL}{path}", timeout=15)
    r.raise_for_status()
    return r.json()

def get_league(lid):             return api_get(f"/league/{lid}")
def get_rosters(lid):            return api_get(f"/league/{lid}/rosters")
def get_users(lid):              return api_get(f"/league/{lid}/users")
def get_matchups(lid, week):     return api_get(f"/league/{lid}/matchups/{week}")
def get_transactions(lid, week): return api_get(f"/league/{lid}/transactions/{week}")
def get_drafts(lid):             return api_get(f"/league/{lid}/drafts")
def get_draft_picks(did):        return api_get(f"/draft/{did}/picks")
def get_winners_bracket(lid):    return api_get(f"/league/{lid}/winners_bracket")
def get_losers_bracket(lid):     return api_get(f"/league/{lid}/losers_bracket")

@st.cache_data(ttl=86400 * 3, show_spinner="Loading player database…")
def get_players():
    return requests.get(f"{BASE_URL}/players/nfl", timeout=60).json()

@st.cache_data(ttl=600)
def get_season_chain(root_id):
    seasons, lid = [], root_id
    while lid and lid != "0":
        try:
            lg = get_league(lid)
            seasons.append(lg)
            lid = lg.get("previous_league_id") or "0"
        except Exception:
            break
    return seasons

@st.cache_data(ttl=300)
def get_season_scores(league_id, last_week):
    rows = []
    for w in range(1, last_week + 1):
        try:
            for m in get_matchups(league_id, w):
                if m.get("points") is not None:
                    rows.append({
                        "week": w, "roster_id": m["roster_id"],
                        "matchup_id": m.get("matchup_id"), "points": m["points"],
                    })
        except Exception:
            pass
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["week","roster_id","matchup_id","points"])

@st.cache_data(ttl=600)
def build_player_team_history(league_ids_tuple):
    """str(pid) → frozenset of roster_ids the player has appeared on across all seasons."""
    history: dict = {}
    for lid in league_ids_tuple:
        try:
            for r in get_rosters(lid):
                rid = r["roster_id"]
                for pid in (r.get("players") or []):
                    spid = str(pid)
                    if spid not in history:
                        history[spid] = set()
                    history[spid].add(rid)
        except Exception:
            pass
    return {k: frozenset(v) for k, v in history.items()}

@st.cache_data(ttl=300)
def get_player_season_pts(league_id, last_week):
    """Aggregate per-player fantasy points from league matchup data (uses league scoring)."""
    pts: dict = {}
    for w in range(1, last_week + 1):
        try:
            for m in get_matchups(league_id, w):
                for pid, fp in (m.get("players_points") or {}).items():
                    pts[str(pid)] = pts.get(str(pid), 0.0) + float(fp)
        except Exception:
            pass
    return pts

@st.cache_data(ttl=300)
def get_all_transactions(league_id, last_week):
    txns = []
    for w in range(1, last_week + 1):
        try:
            week_txns = get_transactions(league_id, w)
            for t in week_txns:
                t["_week"] = w
            txns.extend(week_txns)
        except Exception:
            pass
    return txns

# ─── Helpers ─────────────────────────────────────────────────────────────────

def build_team_map(users, rosters):
    u_map = {u["user_id"]: u for u in users}
    teams = {}
    for r in rosters:
        uid  = r.get("owner_id")
        u    = u_map.get(uid, {})
        meta = u.get("metadata") or {}
        teams[r["roster_id"]] = {
            "display_name": u.get("display_name", "Unknown"),
            "team_name":    meta.get("team_name") or u.get("display_name", "Unknown"),
            "user_id":      uid,
            "roster":       r,
        }
    return teams

def player_info(pid, players):
    p    = players.get(str(pid), {})
    name = f"{p.get('first_name','')} {p.get('last_name','')}".strip() or f"Player {pid}"
    pos  = (p.get("fantasy_positions") or [p.get("position","?")])[0] if p else "?"
    team = p.get("team") or "FA"
    age  = p.get("age") or "?"
    return name, pos, team, age

def fpts(s, key="fpts"):
    return s.get(key, 0) + s.get(f"{key}_decimal", 0) / 100

# ─── Dynasty value model ──────────────────────────────────────────────────────

PEAK_AGES    = {"QB": 28, "WR": 26, "RB": 24, "TE": 27, "K": 30}
POS_BASES    = {"QB": 100, "WR": 85, "TE": 80, "RB": 75, "K": 10}
# Fantasy points a true elite player scores in a season (used to normalize performance)
POS_ELITE_FP = {"QB": 380, "WR": 220, "RB": 220, "TE": 170, "K": 140}

def dynasty_value(pid, players, player_pts=None):
    p    = players.get(str(pid), {})
    pos  = (p.get("fantasy_positions") or [p.get("position","")])[0]
    age  = p.get("age")
    base = POS_BASES.get(pos, 30)

    # Age component — same curve as before
    if not age or pos not in PEAK_AGES:
        age_score = base * 0.5
    else:
        peak = PEAK_AGES[pos]
        if age <= peak:
            mult = 0.5 + 0.5 * max(0.0, 1 - (peak - age) * 0.10)
        else:
            mult = max(0.05, 1 - (age - peak) * 0.13)
        age_score = base * mult

    # Performance component — actual fantasy points from league matchups
    if player_pts is not None:
        fp    = player_pts.get(str(pid), 0.0)
        elite = POS_ELITE_FP.get(pos, 200)
        perf_score = base * min(1.0, fp / elite)
        # 60% recent production, 40% age trajectory
        return round(0.6 * perf_score + 0.4 * age_score, 1)

    return round(age_score, 1)

def roster_total_value(pids, players, player_pts=None):
    return sum(dynasty_value(p, players, player_pts) for p in pids)

# ─── Immaculate Grid ──────────────────────────────────────────────────────────
# Primary mechanic: each row and column is a fantasy team.
# A cell requires a player who was rostered on BOTH the row team AND column team
# at any point in league history.  Occasionally one column is a fun category
# (e.g. "QB" → name a QB ever on that row team).

GRID_SPICE_CATS = [
    {"type": "position", "name": "🏈 QB",    "value": "QB"},
    {"type": "position", "name": "💨 RB",    "value": "RB"},
    {"type": "position", "name": "⚡ WR",    "value": "WR"},
    {"type": "position", "name": "🎯 TE",    "value": "TE"},
    {"type": "age_max",  "name": "Age ≤ 25", "value": 25},
    {"type": "age_min",  "name": "Age 29+",  "value": 29},
]

def _check_grid_item(pid, item, history, players):
    """Return True if pid satisfies this grid item (team presence or category)."""
    if item["type"] == "team":
        return item["value"] in history.get(str(pid), frozenset())
    p   = players.get(str(pid), {})
    pos = (p.get("fantasy_positions") or [p.get("position","")])[0]
    age = p.get("age")
    if item["type"] == "position":  return pos == item["value"]
    if not age:                      return False
    if item["type"] == "age_max":   return age <= item["value"]
    if item["type"] == "age_min":   return age >= item["value"]
    if item["type"] == "age_range":
        lo, hi = item["value"]; return lo <= age <= hi
    return False

def _cell_answers(r_item, c_item, history, players):
    return [pid for pid in history
            if _check_grid_item(pid, r_item, history, players)
            and _check_grid_item(pid, c_item, history, players)]

def normalize_name(s):
    return s.lower().strip().replace(".", "").replace("'", "").replace("-", " ")

def find_player_by_name(guess, players):
    ng = normalize_name(guess)
    for pid, p in players.items():
        full = normalize_name(f"{p.get('first_name','')} {p.get('last_name','')}".strip())
        last = normalize_name(p.get("last_name",""))
        if ng in (full, last):
            return pid
    return None

def _make_team_item(rid, teams_dict):
    t = teams_dict[rid]
    return {"type": "team", "name": t["team_name"], "mgr": t["display_name"], "value": rid}

def generate_valid_grid(teams_dict, history, players, seed):
    rng  = random.Random(seed)
    tids = list(teams_dict.keys())

    for _ in range(600):
        # 85 % pure team-vs-team grid; 15 % one column swapped for a spice category
        use_spice = rng.random() < 0.15 and len(tids) >= 5

        if use_spice:
            shuffled  = rng.sample(tids, 5)
            row_items = [_make_team_item(r, teams_dict) for r in shuffled[:3]]
            col_items = [_make_team_item(r, teams_dict) for r in shuffled[3:5]]
            col_items.append(rng.choice(GRID_SPICE_CATS))
        else:
            shuffled  = rng.sample(tids, min(6, len(tids)))
            row_items = [_make_team_item(r, teams_dict) for r in shuffled[:3]]
            col_items = [_make_team_item(r, teams_dict) for r in shuffled[3:6]]

        # Require every cell to have ≥ 2 distinct valid answers
        if all(
            len(_cell_answers(r, c, history, players)) >= 2
            for r in row_items for c in col_items
        ):
            return row_items, col_items

    # Fallback (should rarely trigger)
    return ([_make_team_item(tids[i], teams_dict) for i in range(3)],
            [_make_team_item(tids[i], teams_dict) for i in range(3, min(6,len(tids)))])

def daily_seed():
    return int(hashlib.md5(date.today().isoformat().encode()).hexdigest(), 16) % (2**31)

# ─── Page: Home ───────────────────────────────────────────────────────────────

def page_home(seasons, players):
    st.title("🏈 CRC Dynasty League")
    completed = [s for s in seasons if s["status"] == "complete"]
    current   = seasons[0]

    # Champion banner
    if completed:
        cl  = completed[0]
        rid = cl.get("metadata", {}).get("latest_league_winner_roster_id")
        cu  = get_users(cl["league_id"])
        cr  = get_rosters(cl["league_id"])
        ct  = build_team_map(cu, cr)
        champ = ct.get(int(rid), {}) if rid else {}
        if champ:
            st.markdown(f"""<div class="champ-banner">
            🏆 <strong style="color:#f9e2af"> {cl['season']} Champion:</strong>
            <span style="color:#cdd6f4;font-size:1.1rem"> {champ['team_name']}</span>
            <span style="color:#a6adc8"> — {champ['display_name']}</span>
            </div>""", unsafe_allow_html=True)

    r1c1, r1c2 = st.columns(2)
    r2c1, r2c2 = st.columns(2)
    starters = len([p for p in current.get("roster_positions",[]) if p not in ("BN","IR","TAXI")])
    for col, label, val, sub in [
        (r1c1, "Current Season", current["season"],        current["status"].replace("_"," ").title()),
        (r1c2, "Seasons",        len(seasons),             f"Since {seasons[-1]['season']}"),
        (r2c1, "Teams",          current["total_rosters"], "Dynasty PPR"),
        (r2c2, "Starters",       starters,                 f"{len(current.get('roster_positions',[]))} total spots"),
    ]:
        col.markdown(f"""<div class="metric-card">
        <div class="label">{label}</div><div class="value">{val}</div><div class="sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown('<div class="sec-hdr">All-Time Records</div>', unsafe_allow_html=True)
    rows = []
    for lg in completed:
        lgr = get_rosters(lg["league_id"])
        lgu = get_users(lg["league_id"])
        lgt = build_team_map(lgu, lgr)
        wid = lg.get("metadata", {}).get("latest_league_winner_roster_id")
        for r in lgr:
            rid = r["roster_id"]
            t   = lgt.get(rid, {})
            s   = r["settings"]
            rows.append({
                "Season":  lg["season"], "Manager": t.get("display_name","?"),
                "Team":    t.get("team_name","?"), "W": s.get("wins",0),
                "L":       s.get("losses",0), "PF": round(fpts(s),2),
                "Champ":   "🏆" if str(rid) == str(wid) else "",
            })

    if rows:
        df  = pd.DataFrame(rows)
        agg = df.groupby("Manager").agg(
            Seasons       = ("Season","count"),
            Wins          = ("W","sum"),
            Losses        = ("L","sum"),
            Total_PF      = ("PF","sum"),
            Championships = ("Champ", lambda x: (x=="🏆").sum()),
        ).reset_index()
        agg["Win%"]    = (agg["Wins"]/(agg["Wins"]+agg["Losses"])*100).round(1)
        agg["Total_PF"]= agg["Total_PF"].round(1)
        agg = agg.sort_values(["Championships","Win%"], ascending=False).reset_index(drop=True)
        agg.index += 1

        col1, col2 = st.columns([2,3])
        with col1:
            st.dataframe(agg.rename(columns={"Total_PF":"Total PF","Championships":"🏆"}),
                         use_container_width=True)
        with col2:
            fig = px.bar(agg, x="Manager", y=["Wins","Losses"],
                         title="All-Time W/L", barmode="stack",
                         color_discrete_map={"Wins":"#a6e3a1","Losses":"#f38ba8"})
            fig.update_layout(height=300, margin=dict(l=0,r=0,t=40,b=0),
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#cdd6f4", legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)

        pivot = df.pivot_table(index="Season", columns="Manager", values="PF", aggfunc="sum")
        fig2  = px.line(pivot.reset_index().melt(id_vars="Season",var_name="Manager",value_name="PF"),
                        x="Season", y="PF", color="Manager",
                        title="Points For by Season", markers=True)
        fig2.update_layout(height=320, margin=dict(l=0,r=0,t=40,b=0),
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font_color="#cdd6f4")
        st.plotly_chart(fig2, use_container_width=True)

# ─── Page: Standings ──────────────────────────────────────────────────────────

def page_standings(seasons, players):
    st.title("📊 Standings")
    completed = [s for s in seasons if s["status"] == "complete"]
    if not completed:
        st.info("No completed seasons yet.")
        return

    opts  = {lg["season"]: lg["league_id"] for lg in completed}
    sel   = st.selectbox("Season", list(opts.keys()), key="standings_season")
    lid   = opts[sel]
    lg    = get_league(lid)
    wrid  = lg.get("metadata",{}).get("latest_league_winner_roster_id")
    teams = build_team_map(get_users(lid), get_rosters(lid))

    rows = []
    for r in get_rosters(lid):
        rid = r["roster_id"]
        t   = teams.get(rid, {})
        s   = r["settings"]
        pf  = fpts(s); pa = fpts(s,"fpts_against"); pp = fpts(s,"ppts")
        rows.append({
            "Team":    t.get("team_name","?"), "Manager": t.get("display_name","?"),
            "W":       s.get("wins",0),        "L":       s.get("losses",0),
            "PF":      round(pf,2),            "PA":      round(pa,2),
            "Max PF":  round(pp,2),            "Eff%":    round(pf/pp*100,1) if pp else 0,
            "":        "🏆" if str(rid)==str(wrid) else "",
        })

    df = pd.DataFrame(rows).sort_values(["W","PF"], ascending=False).reset_index(drop=True)
    df.insert(0,"Rank", range(1,len(df)+1))

    col1, col2 = st.columns([3,2])
    with col1:
        st.dataframe(df, use_container_width=True, height=340, hide_index=True)
    with col2:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df["Max PF"], y=df["Team"], orientation="h",
                             name="Max PF", marker_color="#313244"))
        fig.add_trace(go.Bar(x=df["PF"], y=df["Team"], orientation="h",
                             name="PF", marker_color="#89b4fa"))
        fig.update_layout(title="PF vs Max PF", barmode="overlay", height=340,
                          margin=dict(l=0,r=0,t=40,b=0),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font_color="#cdd6f4")
        st.plotly_chart(fig, use_container_width=True)

    pw    = lg["settings"].get("playoff_week_start", 14)
    last  = lg["settings"].get("last_scored_leg", 17)
    with st.spinner("Loading weekly scores…"):
        scores_df = get_season_scores(lid, pw - 1)

    if not scores_df.empty:
        scores_df["Manager"] = scores_df["roster_id"].map(
            {rid: t["display_name"] for rid, t in teams.items()})

        col1, col2 = st.columns(2)
        with col1:
            fig3 = px.box(scores_df, x="Manager", y="points",
                          title="Score Distribution (Reg Season)", color="Manager")
            fig3.update_layout(height=360, showlegend=False, margin=dict(l=0,r=0,t=40,b=60),
                               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               font_color="#cdd6f4")
            st.plotly_chart(fig3, use_container_width=True)
        with col2:
            fig4 = px.line(scores_df, x="week", y="points", color="Manager",
                           title="Scores by Week", markers=True)
            fig4.update_layout(height=360, margin=dict(l=0,r=0,t=40,b=0),
                               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               font_color="#cdd6f4")
            st.plotly_chart(fig4, use_container_width=True)

# ─── Page: Teams ──────────────────────────────────────────────────────────────

def page_teams(seasons, players):
    st.title("🏟️ Team Rosters")
    opts  = {lg["season"]: lg["league_id"] for lg in seasons}
    sel   = st.selectbox("Season", list(opts.keys()), key="teams_season")
    lid   = opts[sel]
    teams = build_team_map(get_users(lid), get_rosters(lid))
    lg_info   = get_league(lid)
    last_week = lg_info["settings"].get("last_scored_leg", 17)
    player_pts = get_player_season_pts(lid, last_week)

    tnames  = {rid: t["team_name"] for rid, t in teams.items()}
    sel_rid = st.selectbox("Team", list(tnames.keys()), key="teams_team",
                           format_func=lambda x: f"{tnames[x]}  ({teams[x]['display_name']})")
    t   = teams[sel_rid]
    r   = t["roster"]
    s   = r["settings"]
    meta = r.get("metadata") or {}

    tr1c1, tr1c2 = st.columns(2)
    tr2c1, tr2c2 = st.columns(2)
    for col, lbl, val in [
        (tr1c1, "Record",        f"{s.get('wins',0)}–{s.get('losses',0)}"),
        (tr1c2, "Points For",    round(fpts(s),1)),
        (tr2c1, "Points Agnst",  round(fpts(s,'fpts_against'),1)),
        (tr2c2, "Dynasty Value", round(roster_total_value(r.get("players") or [], players, player_pts),0)),
    ]:
        col.markdown(f"""<div class="metric-card">
        <div class="label">{lbl}</div><div class="value">{val}</div></div>""",
        unsafe_allow_html=True)

    st.markdown("")
    starters = set(r.get("starters") or [])
    reserve  = set(r.get("reserve") or [])
    taxi     = set(r.get("taxi") or [])
    all_pids = r.get("players") or []
    bench    = [p for p in all_pids if p not in starters|reserve|taxi]

    def roster_section(title, pids, color):
        if not pids:
            return
        st.markdown(f'<div class="sec-hdr" style="color:{color}">{title}</div>',
                    unsafe_allow_html=True)
        rows = []
        for pid in pids:
            name, pos, nfl, age = player_info(pid, players)
            nick = meta.get(f"p_nick_{pid}", "")
            dv   = dynasty_value(pid, players, player_pts)
            rows.append({"Player": name, "Pos": pos, "NFL": nfl,
                         "Age": age, "Dyn Value": dv, "Nickname": nick})
        df = pd.DataFrame(rows).sort_values(["Pos","Player"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    roster_section("▶ Starters",         list(starters), "#a6e3a1")
    roster_section("🪑 Bench",            bench,          "#89b4fa")
    roster_section("🚑 IR / Reserve",     list(reserve),  "#f38ba8")
    roster_section("🚕 Taxi Squad",       list(taxi),     "#f9e2af")

    # Age analysis
    st.markdown('<div class="sec-hdr">Dynasty Age Analysis</div>', unsafe_allow_html=True)
    age_rows = []
    for pid in all_pids:
        name, pos, _, age = player_info(pid, players)
        if isinstance(age,(int,float)):
            age_rows.append({"Player": name, "Pos": pos, "Age": int(age),
                             "Type": ("Starter" if pid in starters else
                                      "IR" if pid in reserve else
                                      "Taxi" if pid in taxi else "Bench")})
    if age_rows:
        adf  = pd.DataFrame(age_rows)
        avg  = adf["Age"].mean()
        savg = adf[adf["Type"]=="Starter"]["Age"].mean()
        c1,c2 = st.columns(2)
        c1.metric("Avg Roster Age",  f"{avg:.1f}")
        c2.metric("Avg Starter Age", f"{savg:.1f}")
        fig = px.histogram(adf, x="Age", color="Pos", nbins=15,
                           title="Roster Age Distribution",
                           color_discrete_sequence=px.colors.qualitative.Pastel)
        fig.update_layout(height=300, margin=dict(l=0,r=0,t=40,b=0),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font_color="#cdd6f4")
        st.plotly_chart(fig, use_container_width=True)

# ─── Page: Matchups ───────────────────────────────────────────────────────────

def page_matchups(seasons, players):
    st.title("📅 Matchups")
    completed = [s for s in seasons if s["status"]=="complete"]
    if not completed:
        st.info("No completed seasons available.")
        return

    opts = {lg["season"]: lg["league_id"] for lg in completed}
    sel  = st.selectbox("Season", list(opts.keys()), key="matchups_season")
    lid  = opts[sel]
    lg   = get_league(lid)
    last = lg["settings"].get("last_scored_leg", 17)
    pw   = lg["settings"].get("playoff_week_start", 14)
    teams = build_team_map(get_users(lid), get_rosters(lid))

    week = st.slider("Week", 1, last, 1, key="matchups_week")
    mups = get_matchups(lid, week)
    groups: dict = {}
    for m in mups:
        mid = m.get("matchup_id")
        groups.setdefault(mid, []).append(m)

    badge = "🏆 Playoff" if week >= pw else "📆 Regular Season"
    st.markdown(f"**Week {week}** — {badge}")

    for mid, pair in sorted(groups.items()):
        if len(pair) < 2:
            continue
        a, b  = sorted(pair, key=lambda x: x.get("points") or 0, reverse=True)
        ta    = teams.get(a["roster_id"], {})
        tb    = teams.get(b["roster_id"], {})
        pa, pb = a.get("points") or 0, b.get("points") or 0
        c1, cm, c2 = st.columns([5,1,5])
        with c1:
            col = "#a6e3a1" if pa>pb else "#f38ba8"
            st.markdown(f"""<div style="background:#1e1e2e;border:1px solid #313244;
            border-radius:10px;padding:14px 18px">
            <div style="color:#a6adc8;font-size:.8rem">{ta.get('display_name','')}</div>
            <div style="font-size:1.05rem;font-weight:600;color:#cdd6f4">{ta.get('team_name','?')}</div>
            <div style="font-size:2rem;font-weight:800;color:{col}">{pa:.2f}</div></div>""",
            unsafe_allow_html=True)
        with cm:
            st.markdown("<div style='text-align:center;padding-top:28px;color:#6c7086'>vs</div>",
                        unsafe_allow_html=True)
        with c2:
            col = "#a6e3a1" if pb>pa else "#f38ba8"
            st.markdown(f"""<div style="background:#1e1e2e;border:1px solid #313244;
            border-radius:10px;padding:14px 18px;text-align:right">
            <div style="color:#a6adc8;font-size:.8rem">{tb.get('display_name','')}</div>
            <div style="font-size:1.05rem;font-weight:600;color:#cdd6f4">{tb.get('team_name','?')}</div>
            <div style="font-size:2rem;font-weight:800;color:{col}">{pb:.2f}</div></div>""",
            unsafe_allow_html=True)
        st.markdown("")

# ─── Page: Playoffs ───────────────────────────────────────────────────────────

def page_playoffs(seasons, players):
    st.title("🏆 Playoffs")
    completed = [s for s in seasons if s["status"]=="complete"]
    if not completed:
        st.info("No completed seasons available.")
        return

    opts = {lg["season"]: lg["league_id"] for lg in completed}
    sel  = st.selectbox("Season", list(opts.keys()), key="playoffs_season")
    lid  = opts[sel]
    lg   = get_league(lid)
    pw   = lg["settings"].get("playoff_week_start", 14)
    last = lg["settings"].get("last_scored_leg", 17)
    teams = build_team_map(get_users(lid), get_rosters(lid))

    # Fetch bracket + all playoff scores
    try:
        wb = get_winners_bracket(lid)
        lb = get_losers_bracket(lid)
    except Exception:
        st.error("Could not load bracket data.")
        return

    # Build score lookup: (roster_id, week) → points
    score_lookup: dict = {}
    for w in range(pw, last + 1):
        try:
            for m in get_matchups(lid, w):
                score_lookup[(m["roster_id"], w)] = m.get("points", 0)
        except Exception:
            pass

    # Map bracket matchup → week
    # Sleeper bracket rounds: r=1 → first playoff week, r=2 → next, etc.
    def bracket_week(r):
        return pw + r - 1

    def render_bracket(bracket, title):
        st.markdown(f'<div class="sec-hdr">{title}</div>', unsafe_allow_html=True)
        rounds = sorted(set(m["r"] for m in bracket))
        for rnd in rounds:
            matches = [m for m in bracket if m["r"] == rnd]
            w = bracket_week(rnd)
            round_name = ["Quarterfinals","Semifinals","Championship","Final"][min(rnd-1,3)]
            st.markdown(f"**Round {rnd} — {round_name} (Week {w})**")
            cols = st.columns(len(matches))
            for i, match in enumerate(matches):
                t1_id = match.get("t1")
                t2_id = match.get("t2")
                winner = match.get("w")
                t1 = teams.get(t1_id, {})
                t2 = teams.get(t2_id, {})
                s1 = score_lookup.get((t1_id, w), None) if t1_id else None
                s2 = score_lookup.get((t2_id, w), None) if t2_id else None
                with cols[i]:
                    def row(tid, team, score):
                        if tid is None:
                            return "<div style='color:#6c7086;font-size:.85rem'>TBD</div>"
                        is_win = tid == winner
                        name   = team.get("team_name","?")
                        mgr    = team.get("display_name","?")
                        sc_str = f"<span style='font-size:1.2rem;font-weight:700;color:{'#a6e3a1' if is_win else '#cdd6f4'}'>{score:.2f}</span>" if score is not None else ""
                        champ  = " 🏆" if is_win and rnd == max(rounds) else ""
                        return f"""<div style="{'font-weight:700;color:#cdd6f4' if is_win else 'color:#888'}">
                        {name}{champ}<br><span style="font-size:.75rem;color:#6c7086">{mgr}</span><br>{sc_str}</div>"""
                    st.markdown(f"""<div class="bracket-match">
                    {row(t1_id,t1,s1)}<hr style="border-color:#313244;margin:6px 0">
                    {row(t2_id,t2,s2)}</div>""", unsafe_allow_html=True)
            st.markdown("")

    render_bracket(wb, "🥇 Winners Bracket")
    render_bracket(lb, "🥈 Losers Bracket")

# ─── Page: Transactions ───────────────────────────────────────────────────────

def page_transactions(seasons, players):
    st.title("💱 Transactions")
    completed = [s for s in seasons if s["status"]=="complete"]
    if not completed:
        st.info("No completed seasons available.")
        return

    opts = {lg["season"]: lg["league_id"] for lg in completed}
    sel  = st.selectbox("Season", list(opts.keys()), key="txn_season")
    lid  = opts[sel]
    lg   = get_league(lid)
    last = lg["settings"].get("last_scored_leg", 17)
    teams = build_team_map(get_users(lid), get_rosters(lid))

    txn_filter = st.selectbox("Type", ["All","Trade","Waiver / FA"], key="txn_type")

    with st.spinner("Loading transactions…"):
        all_txns = get_all_transactions(lid, last)

    trades  = [t for t in all_txns if t.get("type")=="trade"      and t.get("status")=="complete"]
    waivers = [t for t in all_txns if t.get("type") in ("waiver","free_agent") and t.get("status")=="complete"]

    c1,c2,c3 = st.columns(3)
    for col,lbl,val in [(c1,"Total",len(all_txns)),(c2,"Trades",len(trades)),(c3,"Waivers/FA",len(waivers))]:
        col.markdown(f"""<div class="metric-card">
        <div class="label">{lbl}</div><div class="value">{val}</div></div>""",
        unsafe_allow_html=True)
    st.markdown("")

    if txn_filter in ("All","Trade"):
        st.markdown('<div class="sec-hdr">Trades</div>', unsafe_allow_html=True)
        for txn in sorted(trades, key=lambda x: x.get("created",0), reverse=True):
            rids  = txn.get("roster_ids") or []
            adds  = txn.get("adds") or {}
            picks = txn.get("draft_picks") or []
            ts    = txn.get("created",0)
            dt    = datetime.fromtimestamp(ts/1000).strftime("%b %d") if ts else "?"
            week  = txn.get("_week","?")
            title = " ↔ ".join(teams.get(r,{}).get("team_name",str(r)) for r in rids)
            with st.expander(f"Week {week} — {title}  ({dt})"):
                side_cols = st.columns(max(len(rids),1))
                for i, rid in enumerate(rids):
                    with side_cols[i]:
                        st.markdown(f"**{teams.get(rid,{}).get('team_name',str(rid))}** receives:")
                        received   = [pid for pid,r in adds.items() if r==rid]
                        recv_picks = [p for p in picks if p.get("owner_id")==rid]
                        for pid in received:
                            name, pos, nfl, _ = player_info(pid, players)
                            st.markdown(f"• **{name}** ({pos}, {nfl})")
                        for pk in recv_picks:
                            st.markdown(f"• 📋 {pk.get('season')} Rd {pk.get('round')} pick")

    if txn_filter in ("All","Waiver / FA"):
        st.markdown('<div class="sec-hdr">Waiver / FA Moves</div>', unsafe_allow_html=True)
        rows = []
        for txn in sorted(waivers, key=lambda x: x.get("created",0), reverse=True):
            rids  = txn.get("roster_ids") or []
            adds  = txn.get("adds") or {}
            ts    = txn.get("created",0)
            dt    = datetime.fromtimestamp(ts/1000).strftime("%b %d") if ts else "?"
            bid   = (txn.get("settings") or {}).get("waiver_bid",0)
            tname = teams.get(rids[0],{}).get("team_name",str(rids[0])) if rids else "?"
            for pid, rid in adds.items():
                name, pos, nfl, _ = player_info(pid, players)
                rows.append({"Week":txn.get("_week","?"),"Date":dt,"Team":tname,
                             "Player":name,"Pos":pos,"NFL":nfl,
                             "FAAB":f"${bid}" if bid else "FA"})
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ─── Page: Draft Grades ───────────────────────────────────────────────────────

def page_draft_grades(seasons, players):
    st.title("📜 Draft Grades")
    opts = {lg["season"]: lg["league_id"] for lg in seasons}
    sel  = st.selectbox("Season", list(opts.keys()), key="draft_season")
    lid  = opts[sel]
    teams  = build_team_map(get_users(lid), get_rosters(lid))
    drafts = get_drafts(lid)
    lg_info    = get_league(lid)
    last_week  = lg_info["settings"].get("last_scored_leg", 17)
    player_pts = get_player_season_pts(lid, last_week)

    if not drafts:
        st.info("No draft found for this season.")
        return

    draft  = drafts[0]
    status = draft.get("status","?")
    rounds = draft["settings"].get("rounds",4)
    st.markdown(f"**Type:** {draft.get('type','?').replace('_',' ').title()}  |  "
                f"**Rounds:** {rounds}  |  **Status:** {status.title()}")

    if status == "pre_draft":
        order = draft.get("draft_order") or {}
        if order:
            st.markdown('<div class="sec-hdr">Upcoming Draft Order</div>', unsafe_allow_html=True)
            users = get_users(lid)
            rows = []
            for uid, slot in sorted(order.items(), key=lambda x: x[1]):
                mgr  = next((u.get("display_name","?") for u in users if u["user_id"]==uid),"?")
                team = next((t for t in teams.values() if t["user_id"]==uid),{})
                rows.append({"Slot":slot,"Manager":mgr,"Team":team.get("team_name","?")})
            st.dataframe(pd.DataFrame(rows).sort_values("Slot"),
                         use_container_width=True, hide_index=True)
        return

    with st.spinner("Loading draft picks…"):
        picks = get_draft_picks(draft["draft_id"])

    if not picks:
        st.info("No picks recorded yet.")
        return

    rows = []
    for pk in picks:
        pid  = pk.get("player_id")
        name, pos, nfl, age = player_info(pid, players)
        rid  = pk.get("roster_id") or pk.get("picked_by")
        dv   = dynasty_value(pid, players, player_pts)
        rows.append({
            "Pick":   pk.get("pick_no"),   "Rd":     pk.get("round"),
            "Player": name,                "Pos":    pos,
            "NFL":    nfl,                 "Age":    age,
            "DynVal": dv,                  "Team":   teams.get(rid,{}).get("team_name","?"),
            "Manager":teams.get(rid,{}).get("display_name","?"),
            "_rid":   rid,
        })

    df = pd.DataFrame(rows).sort_values("Pick")

    # Draft grade per team
    st.markdown('<div class="sec-hdr">Draft Grades by Team</div>', unsafe_allow_html=True)

    def pick_grade(avg_val, avg_age):
        score = avg_val * max(0, 1 - max(0, avg_age - 24) * 0.04)
        if score >= 70:  return "A+","#a6e3a1"
        if score >= 60:  return "A", "#a6e3a1"
        if score >= 50:  return "B+","#94e2d5"
        if score >= 42:  return "B", "#89b4fa"
        if score >= 35:  return "C", "#f9e2af"
        if score >= 25:  return "D", "#fab387"
        return "F","#f38ba8"

    grade_rows = []
    for rid, team in teams.items():
        team_picks = df[df["_rid"]==rid]
        if team_picks.empty:
            continue
        avg_val = team_picks["DynVal"].mean()
        ages    = pd.to_numeric(team_picks["Age"], errors="coerce").dropna()
        avg_age = ages.mean() if not ages.empty else 25
        grade, _ = pick_grade(avg_val, avg_age)
        grade_rows.append({
            "Team":    team["team_name"],
            "Manager": team["display_name"],
            "Picks":   len(team_picks),
            "Avg DynVal": round(avg_val,1),
            "Avg Age":    round(avg_age,1),
            "Grade":      grade,
        })

    if grade_rows:
        gdf = pd.DataFrame(grade_rows).sort_values("Avg DynVal", ascending=False)
        col1, col2 = st.columns([2,3])
        with col1:
            st.dataframe(gdf, use_container_width=True, hide_index=True)
        with col2:
            fig = px.bar(gdf, x="Manager", y="Avg DynVal",
                         title="Average Dynasty Value of Picks",
                         color="Avg Age", color_continuous_scale="RdYlGn_r",
                         text="Grade")
            fig.update_traces(textposition="outside")
            fig.update_layout(height=320, margin=dict(l=0,r=0,t=40,b=0),
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#cdd6f4")
            st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="sec-hdr">All Picks</div>', unsafe_allow_html=True)
    pos_opts = ["All"] + sorted(df["Pos"].unique().tolist())
    pos_sel  = st.selectbox("Filter Position", pos_opts, key="draft_pos_filter")
    view_df  = df.drop("_rid",axis=1) if pos_sel=="All" else df[df["Pos"]==pos_sel].drop("_rid",axis=1)
    st.dataframe(view_df, use_container_width=True, hide_index=True)

    fig2 = px.pie(df, names="Pos", title="Pick Distribution by Position",
                  color_discrete_sequence=px.colors.qualitative.Pastel)
    fig2.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font_color="#cdd6f4")
    st.plotly_chart(fig2, use_container_width=True)

# ─── Page: Trade Analyzer ────────────────────────────────────────────────────

def page_trade_analyzer(seasons, players):
    st.title("💰 Trade Analyzer")
    st.caption("Dynasty value blends actual fantasy production (60%) with age trajectory (40%). Use as a guide, not gospel.")

    opts  = {lg["season"]: lg["league_id"] for lg in seasons}
    sel   = st.selectbox("Season", list(opts.keys()), key="trade_season")
    lid   = opts[sel]
    teams = build_team_map(get_users(lid), get_rosters(lid))
    lg_info    = get_league(lid)
    last_week  = lg_info["settings"].get("last_scored_leg", 17)
    player_pts = get_player_season_pts(lid, last_week)

    tnames  = {rid: f"{t['team_name']} ({t['display_name']})" for rid, t in teams.items()}
    t_ids   = list(tnames.keys())

    col1, col2 = st.columns(2)
    with col1:
        rid1 = st.selectbox("Team 1", t_ids, key="trade_t1",
                            format_func=lambda x: tnames[x])
    with col2:
        other = [x for x in t_ids if x != rid1]
        rid2  = st.selectbox("Team 2", other, key="trade_t2",
                             format_func=lambda x: tnames[x])

    r1_pids = teams[rid1]["roster"].get("players") or []
    r2_pids = teams[rid2]["roster"].get("players") or []

    def pid_label(pid):
        name, pos, nfl, age = player_info(pid, players)
        dv = dynasty_value(pid, players, player_pts)
        return f"{name} ({pos}, {nfl}, Age {age}) — Val {dv}"

    st.markdown('<div class="sec-hdr">Build the Trade</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**{teams[rid1]['team_name']} sends:**")
        sends1 = st.multiselect("Players from Team 1", r1_pids, key="trade_sends1",
                                format_func=lambda x: pid_label(x))
    with col2:
        st.markdown(f"**{teams[rid2]['team_name']} sends:**")
        sends2 = st.multiselect("Players from Team 2", r2_pids, key="trade_sends2",
                                format_func=lambda x: pid_label(x))

    if not sends1 and not sends2:
        st.info("Select players above to analyze the trade.")
        return

    # Compute values
    val1_sending = sum(dynasty_value(p, players, player_pts) for p in sends1)
    val2_sending = sum(dynasty_value(p, players, player_pts) for p in sends2)
    diff         = val2_sending - val1_sending  # positive = Team 1 wins

    c1, c2, c3 = st.columns(3)
    c1.markdown(f"""<div class="metric-card">
    <div class="label">{teams[rid1]['team_name']} sends</div>
    <div class="value">{val1_sending:.1f}</div></div>""", unsafe_allow_html=True)
    c2.markdown(f"""<div class="metric-card">
    <div class="label">{teams[rid2]['team_name']} sends</div>
    <div class="value">{val2_sending:.1f}</div></div>""", unsafe_allow_html=True)
    diff_color = "#a6e3a1" if abs(diff) < 10 else ("#f38ba8" if diff < 0 else "#89b4fa")
    winner     = "Fair trade ✓" if abs(diff)<10 else (
                 f"{teams[rid1]['team_name']} wins ↑" if diff>0 else
                 f"{teams[rid2]['team_name']} wins ↑")
    c3.markdown(f"""<div class="metric-card">
    <div class="label">Verdict</div>
    <div class="value" style="color:{diff_color};font-size:1.1rem">{winner}</div>
    <div class="sub">Diff: {abs(diff):.1f} pts</div></div>""", unsafe_allow_html=True)

    # Side-by-side player breakdown
    st.markdown('<div class="sec-hdr">Player Breakdown</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    for col, sends, rid in [(col1, sends1, rid1), (col2, sends2, rid2)]:
        with col:
            st.markdown(f"**{teams[rid]['team_name']}** sending:")
            if sends:
                rows = []
                for pid in sends:
                    name, pos, nfl, age = player_info(pid, players)
                    rows.append({"Player":name,"Pos":pos,"NFL":nfl,
                                 "Age":age,"DynVal":dynasty_value(pid,players,player_pts)})
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.caption("Nothing selected")

# ─── Page: Immaculate Grid ────────────────────────────────────────────────────

def _build_grid_html(row_items, col_items, current_answers, results, submitted):
    """Return a self-contained HTML table representing the 4×4 grid."""
    B = "border:2px solid #313244"
    P = "padding:8px 6px;text-align:center;vertical-align:middle"
    H = f"{B};{P};font-weight:700;font-size:.82rem;line-height:1.35;height:76px"

    html = ('<table style="width:100%;border-collapse:collapse;'
            'table-layout:fixed;margin-bottom:4px">')

    # Column header row
    html += '<tr>'
    html += f'<td style="{H};background:#181825;font-size:1.4rem">🏈</td>'
    for c in col_items:
        if c["type"] == "team":
            sub = (f'<br><span style="font-size:.65rem;font-weight:400;color:#6c7086">'
                   f'{c["mgr"]}</span>')
            html += f'<td style="{H};background:#313244;color:#cdd6f4">{c["name"]}{sub}</td>'
        else:
            html += f'<td style="{H};background:#45475a;color:#f9e2af">{c["name"]}</td>'
    html += '</tr>'

    # Data rows
    for i, r in enumerate(row_items):
        html += '<tr>'
        sub = (f'<br><span style="font-size:.65rem;font-weight:400;color:#6c7086">'
               f'{r["mgr"]}</span>')
        html += f'<td style="{H};background:#313244;color:#cdd6f4">{r["name"]}{sub}</td>'
        for j in range(3):
            if submitted:
                res = results.get((i, j), {})
                ok  = res.get("correct", False)
                txt = res.get("player") or res.get("guess") or "—"
                ico = "✅" if ok else "❌"
                bg  = "#a6e3a115" if ok else "#f38ba815"
                bdr = "#a6e3a1"   if ok else "#f38ba8"
                html += (f'<td style="background:{bg};border:2px solid {bdr};{P};height:76px;'
                         f'font-size:.75rem;color:#cdd6f4;word-break:break-word;line-height:1.4">'
                         f'{ico}<br>{txt}</td>')
            else:
                ans  = current_answers.get((i, j), "").strip()
                disp = (ans[:13] + "…") if len(ans) > 13 else ans
                if ans:
                    html += (f'<td style="background:#313244;border:2px solid #89b4fa;{P};'
                             f'height:76px;font-size:.75rem;color:#89b4fa;line-height:1.4">'
                             f'✏️ {disp}</td>')
                else:
                    html += (f'<td style="background:#1e1e2e;border:2px solid #45475a;{P};'
                             f'height:76px;font-size:1.6rem;color:#313244">?</td>')
        html += '</tr>'

    html += '</table>'
    return html

def page_immaculate_grid(seasons, players):
    st.title("🎮 Immaculate Grid")
    today = date.today()
    st.caption(
        f"{today.strftime('%B %d, %Y')}  ·  Name a player rostered on "
        f"**both** teams (row × column) at any point in league history  ·  Resets at midnight"
    )

    current_lid = seasons[0]["league_id"]
    teams = build_team_map(get_users(current_lid), get_rosters(current_lid))

    with st.spinner("Building league history…"):
        history = build_player_team_history(tuple(lg["league_id"] for lg in seasons))

    with st.spinner("Generating today's grid…"):
        row_items, col_items = generate_valid_grid(teams, history, players, daily_seed())

    # ── Session state ─────────────────────────────────────────────────────────
    if st.session_state.get("ig_date") != str(today):
        st.session_state.ig_date      = str(today)
        st.session_state.ig_submitted = False
        st.session_state.ig_results   = {}
        st.session_state.ig_score     = 0

    submitted = st.session_state.ig_submitted

    # ── Visual grid (HTML table — always shown) ───────────────────────────────
    current_answers = {
        (i, j): st.session_state.get(f"ig_g_{i}_{j}", "")
        for i in range(3) for j in range(3)
    }
    st.markdown(
        _build_grid_html(row_items, col_items, current_answers,
                         st.session_state.ig_results, submitted),
        unsafe_allow_html=True,
    )

    # ── Input phase ───────────────────────────────────────────────────────────
    if not submitted:
        st.markdown('<div class="sec-hdr">Your Answers</div>', unsafe_allow_html=True)
        with st.form("ig_form"):
            for i, r_item in enumerate(row_items):
                st.markdown(
                    f'<div style="font-size:.88rem;font-weight:700;color:#89b4fa;'
                    f'margin:10px 0 4px;padding-left:6px;border-left:3px solid #89b4fa">'
                    f'{r_item["name"]} '
                    f'<span style="font-weight:400;color:#6c7086;font-size:.75rem">'
                    f'({r_item["mgr"]})</span></div>',
                    unsafe_allow_html=True,
                )
                cells = st.columns(3)
                for j, c_item in enumerate(col_items):
                    cells[j].text_input(
                        c_item["name"],
                        key=f"ig_g_{i}_{j}",
                        placeholder="Player…",
                    )
            go = st.form_submit_button(
                "✓ Submit All Answers", use_container_width=True, type="primary"
            )

        if go:
            used_pids: set = set()
            res, score = {}, 0
            for i, r_item in enumerate(row_items):
                for j, c_item in enumerate(col_items):
                    guess = st.session_state.get(f"ig_g_{i}_{j}", "").strip()
                    if not guess:
                        res[(i, j)] = {"correct": False, "guess": ""}
                        continue
                    pid   = find_player_by_name(guess, players)
                    valid = (
                        pid is not None
                        and pid not in used_pids
                        and _check_grid_item(pid, r_item, history, players)
                        and _check_grid_item(pid, c_item, history, players)
                    )
                    if valid:
                        name = player_info(pid, players)[0]
                        res[(i, j)] = {"correct": True, "guess": guess, "player": name}
                        used_pids.add(pid)
                        score += 1
                    else:
                        res[(i, j)] = {"correct": False, "guess": guess}
            st.session_state.ig_submitted = True
            st.session_state.ig_results   = res
            st.session_state.ig_score     = score
            st.rerun()

    # ── Results phase ─────────────────────────────────────────────────────────
    else:
        score = st.session_state.ig_score
        emoji = "🏆" if score == 9 else "🔥" if score >= 7 else "👍" if score >= 5 else "😬"
        color = "#a6e3a1" if score >= 7 else "#f9e2af" if score >= 4 else "#f38ba8"
        st.markdown(
            f'<div style="text-align:center;font-size:2.2rem;font-weight:800;'
            f'color:{color};margin:4px 0 16px">{emoji}  {score} / 9</div>',
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)
        reveal = col1.button("👁️ Reveal Answers", key="ig_reveal")
        col2.button("🔄 Play Again", key="ig_retry",
                    on_click=lambda: st.session_state.update(
                        ig_submitted=False, ig_results={}, ig_score=0,
                        **{f"ig_g_{i}_{j}": "" for i in range(3) for j in range(3)}
                    ))

        if reveal:
            st.markdown('<div class="sec-hdr">All Valid Answers</div>',
                        unsafe_allow_html=True)
            for i, r_item in enumerate(row_items):
                for j, c_item in enumerate(col_items):
                    answers = _cell_answers(r_item, c_item, history, players)
                    names   = sorted(player_info(p, players)[0] for p in answers)
                    label   = f"**{r_item['name']}** × **{c_item['name']}**"
                    st.markdown(
                        f"{label}: "
                        f'<span style="color:#a6adc8;font-size:.85rem">'
                        f'{", ".join(names[:10])}{"…" if len(names)>10 else ""}</span>',
                        unsafe_allow_html=True,
                    )

    # ── Rules ─────────────────────────────────────────────────────────────────
    with st.expander("How to play"):
        st.markdown("""
**Rows** and **columns** are each a fantasy team from your league (6 different teams).

For each of the 9 cells, name a player who was **on both** the row team and the column team
at any point in league history (any season since 2023).

- Each player can only be used **once** across the whole grid
- Type a player's full name or last name only
- Occasionally one column is a fun category (QB, Age ≤ 25, etc.) — then just name any player
  on that row team matching the category
- The puzzle is the same for everyone and resets every night at midnight
        """)

# ─── Page: League Stats ───────────────────────────────────────────────────────

GSHEET_CSV = (
    "https://docs.google.com/spreadsheets/d/"
    "1u05ZjYbM-Hj46bnAh9R9aF7QHXQtKNR_YADQhhVnI1M/export?format=csv"
)

@st.cache_data(ttl=3600, show_spinner="Loading league stats…")
def fetch_gsheet():
    return pd.read_csv(GSHEET_CSV)

def page_league_stats():
    st.title("📈 League Stats")
    st.caption("Data pulled automatically from the CRC Dynasty Google Sheet · refreshes every hour.")

    try:
        df = fetch_gsheet()
    except Exception as e:
        st.error(f"Could not load the Google Sheet: {e}")
        return

    # Normalise column names
    df.columns = [c.strip() for c in df.columns]

    tab_season, tab_alltime, tab_playoffs = st.tabs(
        ["📅 Current Season", "📊 All-Time", "🏆 Playoffs"]
    )

    # ── Current Season ────────────────────────────────────────────────────────
    with tab_season:
        season_cols = ["Name", "Wins", "Losses", "Win %", "Streak",
                       "Points For", "Points Ag", "Point Dif", "AVG PPG", "AVG AG"]
        avail = [c for c in season_cols if c in df.columns]
        sdf   = df[avail].copy()

        if "Wins" in sdf.columns:
            sdf = sdf.sort_values("Wins", ascending=False).reset_index(drop=True)
            sdf.index = range(1, len(sdf) + 1)

        st.dataframe(sdf, use_container_width=True)

        # Bar chart — points for
        if "Points For" in df.columns and "Name" in df.columns:
            chart_df = df[["Name", "Points For", "Points Ag"]].copy()
            chart_df = chart_df.sort_values("Points For", ascending=False)
            fig = px.bar(
                chart_df.melt(id_vars="Name", var_name="Type", value_name="Points"),
                x="Name", y="Points", color="Type", barmode="group",
                title="Points For vs Points Against",
                color_discrete_map={"Points For": "#89b4fa", "Points Ag": "#f38ba8"},
            )
            fig.update_layout(
                height=340, margin=dict(l=0, r=0, t=40, b=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#cdd6f4", legend_title_text="",
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── All-Time ──────────────────────────────────────────────────────────────
    with tab_alltime:
        at_cols = ["Name", "TotalW", "TotalL", "TotalW%",
                   "Total PF", "Total PA", "Total Dif", "WkWon", "WkLost"]
        avail = [c for c in at_cols if c in df.columns]
        atdf  = df[avail].copy()

        rename = {
            "TotalW": "W", "TotalL": "L", "TotalW%": "Win %",
            "Total PF": "PF", "Total PA": "PA", "Total Dif": "PF Diff",
            "WkWon": "Wk Won", "WkLost": "Wk Lost",
        }
        atdf = atdf.rename(columns={k: v for k, v in rename.items() if k in atdf.columns})

        if "W" in atdf.columns:
            atdf = atdf.sort_values("W", ascending=False).reset_index(drop=True)
            atdf.index = range(1, len(atdf) + 1)

        st.dataframe(atdf, use_container_width=True)

        if "Win %" in atdf.columns and "Name" in atdf.columns:
            fig2 = px.bar(
                atdf.reset_index().rename(columns={"index": "Rank"}),
                x="Name", y="Win %", title="All-Time Win %",
                color="Win %", color_continuous_scale="Blues", text="Win %",
            )
            fig2.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig2.update_layout(
                height=340, margin=dict(l=0, r=0, t=40, b=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#cdd6f4", showlegend=False, coloraxis_showscale=False,
            )
            st.plotly_chart(fig2, use_container_width=True)

    # ── Playoffs ──────────────────────────────────────────────────────────────
    with tab_playoffs:
        po_cols = ["Name", "ChampsMade", "CHAMPSWON", "#1 Seed", "Last Place",
                   "Playoff W", "Playoff L", "Playoff W%", "Playoff PF", "Playoff PA"]
        avail = [c for c in po_cols if c in df.columns]
        podf  = df[avail].copy()

        rename_po = {
            "ChampsMade": "Finals", "CHAMPSWON": "🏆 Champs",
            "#1 Seed": "1st Seeds", "Last Place": "Last Place",
            "Playoff W": "PO W", "Playoff L": "PO L",
            "Playoff W%": "PO Win%", "Playoff PF": "PO PF", "Playoff PA": "PO PA",
        }
        podf = podf.rename(columns={k: v for k, v in rename_po.items() if k in podf.columns})

        if "🏆 Champs" in podf.columns:
            podf = podf.sort_values("🏆 Champs", ascending=False).reset_index(drop=True)
            podf.index = range(1, len(podf) + 1)

        st.dataframe(podf, use_container_width=True)

        # Champions bar
        if "🏆 Champs" in podf.columns and "Finals" in podf.columns:
            honor_cols = [c for c in ["🏆 Champs", "Finals", "1st Seeds"] if c in podf.columns]
            fig3 = px.bar(
                podf.reset_index()[["Name"] + honor_cols].melt(
                    id_vars="Name", var_name="Honor", value_name="Count"
                ),
                x="Name", y="Count", color="Honor", barmode="group",
                title="Championship Accolades",
                color_discrete_sequence=["#f9e2af", "#fab387", "#89b4fa"],
            )
            fig3.update_layout(
                height=320, margin=dict(l=0, r=0, t=40, b=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#cdd6f4", legend_title_text="",
            )
            st.plotly_chart(fig3, use_container_width=True)

# ─── Page: Wiki ───────────────────────────────────────────────────────────────

def page_wiki():
    st.title("📖 League Wiki")
    st.caption("Everything you need to know about the CRC Dynasty Dashboard.")

    # ── About ─────────────────────────────────────────────────────────────────
    with st.expander("🏈 About This App", expanded=True):
        st.markdown("""
**CRC Dynasty Dashboard** is a custom-built web app for the CRC Dynasty Fantasy Football League,
built and maintained by **Ryan Leo**.

The goal is to give every manager a single place to track standings, rosters, matchups, trades,
and dynasty value — without having to dig through Sleeper's native UI for everything.
All data is pulled live from the **Sleeper API**, so scores and rosters are always up to date.

The app was built with **Python + Streamlit** and runs directly in your browser.
No login required — just open the link and go.
        """)

    # ── Dynasty Value ─────────────────────────────────────────────────────────
    with st.expander("💎 How Dynasty Value Is Calculated"):
        st.markdown("""
Dynasty value is a single number that estimates how much a player is worth to a dynasty roster right now.
It blends two things:

**1. Recent Fantasy Production (60% weight)**
The player's actual fantasy points scored in the selected season — using your league's own scoring settings,
pulled directly from Sleeper. A player who scored at the level of a true elite finisher at their position
earns a full performance score. A player who barely appeared scores near zero.

| Position | "Elite" season (full score) |
|----------|-----------------------------|
| QB | 380 pts |
| WR | 220 pts |
| RB | 220 pts |
| TE | 170 pts |
| K  | 140 pts |

**2. Age Trajectory (40% weight)**
A curve based on when each position typically peaks. Young players still climbing toward their peak
score higher than veterans on the decline — even with similar recent production.

| Position | Peak Age |
|----------|----------|
| QB | 28 |
| WR | 26 |
| RB | 24 |
| TE | 27 |

- **Before peak:** value ramps from 50% → 100% of the position base as the player approaches their peak age
- **After peak:** value drops ~13% per year past peak, floored at 5%

**Position Base Values** (the ceiling each position can reach): QB 100, WR 85, TE 80, RB 75, K 10.

**Why blend both?**
Pure age-based value ignores actual performance — a busted young RB still looks valuable.
Pure production ignores upside — a 22-year-old breakout WR is worth more than his one good season suggests.
The blend rewards players who are both producing *and* young.

> **Note:** Players without age data or who didn't appear in league matchups fall back to the age-only estimate.
        """)

    # ── Standings ─────────────────────────────────────────────────────────────
    with st.expander("📊 Standings & Stats Explained"):
        st.markdown("""
| Column | Meaning |
|--------|---------|
| **W / L** | Regular season wins and losses |
| **PF** | Points For — total fantasy points scored |
| **PA** | Points Against — total points scored against you |
| **Max PF** | Maximum possible points — what you *would* have scored with a perfect lineup every week |
| **Eff%** | Efficiency — PF ÷ Max PF. Measures how well managers set their lineups. 100% = perfect every week |

The **PF vs Max PF** chart shows the gap between what you scored and what you left on the bench.
A small gap means good lineup management. A large gap means you left points sitting on your bench.
        """)

    # ── Draft Lottery ─────────────────────────────────────────────────────────
    with st.expander("🎰 Draft Lottery — How It Works"):
        st.markdown("""
The draft lottery determines pick order for the following season's rookie/free agent draft.
Only the **4 non-playoff teams** are entered.

**Odds (weighted by finish):**
| Finish | Odds of 1st Pick |
|--------|-----------------|
| 8th (Last) | 40% |
| 7th | 30% |
| 6th | 20% |
| 5th | 10% |

**How the draw works:**
Each pick slot is drawn independently using weighted random selection — but without replacement.
Once a team wins a pick slot, they're removed from the remaining draw.
This means every team is guaranteed *a* pick, but the best odds go to the worst finishers.

**The reveal** goes from 4th pick down to 1st overall — the most dramatic result last.
Use this tool live with your league on draft night!
        """)

    # ── Immaculate Grid ───────────────────────────────────────────────────────
    with st.expander("🎮 Immaculate Grid — How to Play"):
        st.markdown("""
A daily trivia challenge inspired by the MLB Immaculate Grid, adapted for your dynasty league.

**Setup:**
- The grid is **3 rows × 3 columns** — each row and column is one of your league's fantasy teams
- Each of the 9 cells requires a player who was on **both** the row team *and* the column team
  at some point across the full history of the league (every season since the league started)

**Rules:**
- Each player can only be used **once** — you can't put the same player in two cells
- Type a player's full name or just their last name
- Occasionally one column is a **special category** instead of a team (e.g. "QB", "Age ≤ 25") —
  for those, name any player on the row team who fits the category
- The puzzle is the **same for everyone** each day and resets at midnight

**Scoring:** 1 point per correct answer, 9 possible.
        """)

    # ── League Voting ─────────────────────────────────────────────────────────
    with st.expander("🗳️ League Voting — How It Works"):
        st.markdown("""
The voting system lets the league propose and vote on rule changes without needing a group chat thread.

**Creating a proposal:**
Anyone can submit a proposal with a title, description, and the season it would take effect if passed.

**Voting:**
Select your manager name and vote Yes or No. You can change your vote at any time while the proposal is open.

**Closing a proposal:**
Any manager can click "Close & Record Verdict" when the league is done deliberating.
The result is determined by simple majority — more Yes votes than No votes = **Passed**.

**History:**
All closed proposals (passed and failed) are recorded permanently in the Vote History tab,
including the final vote count and implementation season.
        """)

    # ── Data & Privacy ────────────────────────────────────────────────────────
    with st.expander("🔒 Data & Privacy"):
        st.markdown("""
- All fantasy data comes from the **Sleeper public API** — no login or credentials required
- Player data is cached for **72 hours**; league/roster data refreshes every **5 minutes**
- The voting system stores data locally in a `votes.json` file on the server hosting the app
- No personal data beyond your Sleeper display name is stored anywhere
        """)

    # ── FAQ ───────────────────────────────────────────────────────────────────
    with st.expander("❓ FAQ"):
        st.markdown("""
**Q: Why doesn't my roster show the latest adds/drops?**
A: Roster data is cached for 5 minutes. Wait a few minutes and refresh the page.

**Q: The dynasty value for my player seems too low / high. Why?**
A: Value is based on your league's own matchup scoring for the *selected season*.
If you're viewing a past season, it reflects that season's production.
Players who were injured or barely played will show low values regardless of age.

**Q: Can I use the lottery tool before the season ends?**
A: Yes — it pulls from any completed season. If the current season isn't complete yet,
select the most recent finished season to get the right standings.

**Q: The immaculate grid seems impossible. Are there always valid answers?**
A: Yes — the grid generator requires every cell to have at least **2 distinct valid answers**
before it's shown. If it can't find a valid grid after 600 attempts, it falls back to the easiest layout.

**Q: How do I get the app updated with new features?**
A: Contact Ryan — or submit a voting proposal in the League Voting tool. 😄
        """)

# ─── Voting helpers ───────────────────────────────────────────────────────────

VOTES_FILE = Path(__file__).parent / "votes.json"

def _load_votes():
    if VOTES_FILE.exists():
        try:
            return json.loads(VOTES_FILE.read_text())
        except Exception:
            pass
    return {"proposals": []}

def _save_votes(data):
    VOTES_FILE.write_text(json.dumps(data, indent=2))

# ─── Tool: Draft Lottery ──────────────────────────────────────────────────────

def _tool_lottery(seasons):
    st.caption(
        "The 4 non-playoff teams draw for draft position. "
        "Last place (8th) gets 40% odds, 7th → 30%, 6th → 20%, 5th → 10%. "
        "Picks are drawn without replacement — most exciting reveal last."
    )

    all_seasons = [s for s in seasons if s["status"] in ("complete", "in_season", "post_season")]
    if not all_seasons:
        st.info("No seasons found.")
        return

    opts = {s["season"]: s["league_id"] for s in all_seasons}
    sel  = st.selectbox("Season", list(opts.keys()), key="lot_season")
    lid  = opts[sel]

    rosters = get_rosters(lid)
    teams   = build_team_map(get_users(lid), rosters)

    # Sort worst → best (ascending wins, ascending PF as tiebreak)
    sorted_rosters = sorted(
        rosters,
        key=lambda r: (r["settings"].get("wins", 0), fpts(r["settings"]))
    )
    bottom4 = sorted_rosters[:4]
    b4_rids = [r["roster_id"] for r in bottom4]
    odds    = [40, 30, 20, 10]

    st.markdown('<div class="sec-hdr">Lottery Participants</div>', unsafe_allow_html=True)
    cols   = st.columns(4)
    labels = ["🔴 Last (8th)", "🟠 7th", "🟡 6th", "🟢 5th"]
    for i, (rid, pct) in enumerate(zip(b4_rids, odds)):
        t = teams.get(rid, {})
        s = bottom4[i]["settings"]
        cols[i].markdown(f"""<div class="metric-card">
        <div class="label">{labels[i]}</div>
        <div class="value" style="font-size:1rem">{t.get('team_name','?')}</div>
        <div class="sub">{t.get('display_name','')} · {s.get('wins',0)}–{s.get('losses',0)}</div>
        <div style="color:#f9e2af;font-weight:700;font-size:1.2rem;margin-top:6px">{pct}%</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    # Reset state when season changes
    skey = f"lottery_{sel}"
    if st.session_state.get("_lottery_skey") != skey:
        st.session_state._lottery_skey   = skey
        st.session_state._lottery_result = None
        st.session_state._lottery_step   = 0

    if st.session_state._lottery_result is None:
        if st.button("🎰 Run Lottery", type="primary", key="run_lot"):
            remaining = list(zip(b4_rids, odds))
            order = []
            for _ in range(4):
                rids_left, weights = zip(*remaining)
                winner = random.choices(rids_left, weights=weights)[0]
                order.append(winner)
                remaining = [(r, w) for r, w in remaining if r != winner]
            st.session_state._lottery_result = order  # [1st-pick winner, 2nd, 3rd, 4th]
            st.session_state._lottery_step   = 0
            st.rerun()
        return

    result = st.session_state._lottery_result
    step   = st.session_state._lottery_step  # picks revealed so far (0→4, from 4th down to 1st)

    pick_labels = ["🥇 1st Overall", "🥈 2nd Overall", "🥉 3rd Overall", "4️⃣ 4th Overall"]

    st.markdown('<div class="sec-hdr">Draft Order Reveal</div>', unsafe_allow_html=True)

    # Display from 4th pick to 1st (reveal in that order)
    for display_pos in range(4):          # display_pos 0 = 4th pick, 3 = 1st pick
        pick_idx   = 3 - display_pos      # index into result[] (3 = 4th pick)
        is_revealed = step > display_pos

        t = teams.get(result[pick_idx], {})
        s = next((r["settings"] for r in sorted_rosters if r["roster_id"] == result[pick_idx]), {})

        if is_revealed:
            gold = pick_idx == 0  # 1st overall
            bg     = "#f9e2af22" if gold else "#1e1e2e"
            border = "#f9e2af"   if gold else "#313244"
            st.markdown(
                f'<div style="background:{bg};border:2px solid {border};border-radius:10px;'
                f'padding:14px 20px;margin-bottom:8px">'
                f'<span style="color:#a6adc8;font-size:.8rem">{pick_labels[pick_idx]}</span><br>'
                f'<span style="color:#cdd6f4;font-size:1.15rem;font-weight:700">{t.get("team_name","?")}</span>'
                f'<span style="color:#6c7086;font-size:.85rem;margin-left:10px">{t.get("display_name","")}</span>'
                f'<span style="color:#6c7086;font-size:.8rem;margin-left:10px">'
                f'{s.get("wins",0)}–{s.get("losses",0)}</span>'
                f'</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f'<div style="background:#181825;border:2px dashed #45475a;border-radius:10px;'
                f'padding:14px 20px;margin-bottom:8px;color:#6c7086">'
                f'<span style="font-size:.8rem">{pick_labels[pick_idx]}</span>'
                f'&nbsp;&nbsp;<span style="font-size:1rem">🎴 Not yet revealed</span></div>',
                unsafe_allow_html=True
            )

    st.markdown("")

    if step < 4:
        next_label = ["4th", "3rd", "2nd", "1st"][step]
        suffix     = " 🎉" if step == 3 else ""
        if st.button(f"🎰 Reveal {next_label} Pick{suffix}", type="primary", key=f"lot_reveal_{step}"):
            st.session_state._lottery_step += 1
            if st.session_state._lottery_step == 4:
                st.balloons()
            st.rerun()
    else:
        st.success("🏆 Lottery complete!")
        if st.button("🔄 Reset", key="lot_reset"):
            st.session_state._lottery_result = None
            st.session_state._lottery_step   = 0
            st.rerun()

# ─── Tool: League Voting ──────────────────────────────────────────────────────

def _tool_voting(seasons):
    current_lid   = seasons[0]["league_id"]
    teams         = build_team_map(get_users(current_lid), get_rosters(current_lid))
    manager_names = sorted(t["display_name"] for t in teams.values())

    data      = _load_votes()
    proposals = data.setdefault("proposals", [])

    vt_active, vt_new, vt_history = st.tabs(["📋 Active Proposals", "➕ New Proposal", "📚 Vote History"])

    # ── Active ────────────────────────────────────────────────────────────────
    with vt_active:
        active = [p for p in proposals if p["status"] == "open"]
        if not active:
            st.info("No open proposals. Create one in the 'New Proposal' tab.")

        voter = st.selectbox(
            "Voting as:",
            ["— select your name —"] + manager_names,
            key="voter_id"
        )

        for prop in active:
            yes_count = sum(1 for v in prop["votes"].values() if v == "yes")
            no_count  = sum(1 for v in prop["votes"].values() if v == "no")
            total     = len(teams)

            with st.expander(f"📜 {prop['title']}", expanded=True):
                if prop.get("description"):
                    st.markdown(prop["description"])
                impl = prop.get("impl_season","")
                st.caption(
                    f"Opened: {prop['created_date']}  |  "
                    f"League season: {prop.get('season','?')}"
                    + (f"  |  Implements: {impl}" if impl else "")
                )

                c1, c2, c3 = st.columns(3)
                c1.metric("✅ Yes", yes_count)
                c2.metric("❌ No",  no_count)
                c3.metric("🗳️ Voted", f"{yes_count + no_count} / {total}")

                if voter != "— select your name —":
                    existing = prop["votes"].get(voter)
                    cy, cn   = st.columns(2)
                    if cy.button("✅ Vote Yes", key=f"y_{prop['id']}",
                                 type="primary" if existing == "yes" else "secondary"):
                        prop["votes"][voter] = "yes"
                        _save_votes(data)
                        st.rerun()
                    if cn.button("❌ Vote No",  key=f"n_{prop['id']}",
                                 type="primary" if existing == "no"  else "secondary"):
                        prop["votes"][voter] = "no"
                        _save_votes(data)
                        st.rerun()
                    if existing:
                        st.caption(f"Your current vote: **{existing.upper()}**")

                if st.button("Close & Record Verdict", key=f"close_{prop['id']}"):
                    prop["status"] = "passed" if yes_count > no_count else "failed"
                    _save_votes(data)
                    st.rerun()

    # ── New proposal ──────────────────────────────────────────────────────────
    with vt_new:
        st.markdown("#### Create a New Proposal")
        with st.form("new_proposal_form"):
            title       = st.text_input("Rule / Proposal Title")
            desc        = st.text_area("Description / Details")
            impl_season = st.text_input(
                "Implementation Season (if passed)",
                placeholder="e.g. 2026"
            )
            submitted = st.form_submit_button("Submit Proposal", type="primary")

        if submitted:
            if not title.strip():
                st.error("Please enter a title.")
            else:
                proposals.append({
                    "id":           uuid.uuid4().hex[:8],
                    "title":        title.strip(),
                    "description":  desc.strip(),
                    "created_date": date.today().isoformat(),
                    "season":       seasons[0]["season"],
                    "impl_season":  impl_season.strip(),
                    "status":       "open",
                    "votes":        {},
                })
                _save_votes(data)
                st.success(f"Proposal '{title.strip()}' created!")
                st.rerun()

    # ── History ───────────────────────────────────────────────────────────────
    with vt_history:
        closed = [p for p in proposals if p["status"] in ("passed", "failed")]
        if not closed:
            st.info("No closed proposals yet.")
        else:
            for p in sorted(closed, key=lambda x: x["created_date"], reverse=True):
                passed = p["status"] == "passed"
                bg     = "#a6e3a122" if passed else "#f38ba822"
                border = "#a6e3a1"   if passed else "#f38ba8"
                icon   = "✅ PASSED" if passed else "❌ FAILED"
                yes_v  = sum(1 for v in p["votes"].values() if v == "yes")
                no_v   = sum(1 for v in p["votes"].values() if v == "no")
                impl   = f" · Implementing {p['impl_season']}" if p.get("impl_season") else ""
                st.markdown(
                    f'<div style="background:{bg};border:1px solid {border};border-radius:10px;'
                    f'padding:14px 20px;margin-bottom:10px">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center">'
                    f'<span style="color:#cdd6f4;font-size:1rem;font-weight:700">{p["title"]}</span>'
                    f'<span style="color:{border};font-size:.85rem;font-weight:700">{icon}</span></div>'
                    + (f'<div style="color:#a6adc8;font-size:.85rem;margin-top:4px">{p["description"]}</div>' if p.get("description") else "")
                    + f'<div style="color:#6c7086;font-size:.75rem;margin-top:6px">'
                    f'{p["created_date"]} · {yes_v} yes / {no_v} no{impl}</div></div>',
                    unsafe_allow_html=True
                )

# ─── Page: Tools & Links ──────────────────────────────────────────────────────

def page_tools(seasons, players):
    st.title("🛠️ Tools & Links")

    st.markdown('<div class="sec-hdr">🔗 Links</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    for col, name, url, desc in [
        (c1, "Sleeper",       "https://sleeper.com",       "League management, scoring & chat"),
        (c2, "KeepTradeCut",  "https://keeptradecut.com",  "Dynasty player values & rankings"),
    ]:
        col.markdown(
            f'<div class="metric-card" style="text-align:left">'
            f'<a href="{url}" target="_blank" style="color:#89b4fa;font-size:1.05rem;'
            f'font-weight:700;text-decoration:none">{name} ↗</a>'
            f'<div class="sub" style="margin-top:4px">{desc}</div></div>',
            unsafe_allow_html=True
        )

    st.markdown("")
    tool_tab1, tool_tab2 = st.tabs(["🎰 Draft Lottery", "🗳️ League Voting"])

    with tool_tab1:
        _tool_lottery(seasons)

    with tool_tab2:
        _tool_voting(seasons)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    with st.spinner("Loading league…"):
        seasons = get_season_chain(LEAGUE_ID)
        players = get_players()

    tabs = st.tabs([
        "🏠 Home", "📊 Standings", "🏟️ Teams", "📅 Matchups",
        "🏆 Playoffs", "💱 Transactions", "📜 Drafts",
        "💰 Values", "🎮 Grid", "🛠️ Tools", "📈 Stats", "📖 Wiki",
    ])
    with tabs[0]:  page_home(seasons, players)
    with tabs[1]:  page_standings(seasons, players)
    with tabs[2]:  page_teams(seasons, players)
    with tabs[3]:  page_matchups(seasons, players)
    with tabs[4]:  page_playoffs(seasons, players)
    with tabs[5]:  page_transactions(seasons, players)
    with tabs[6]:  page_draft_grades(seasons, players)
    with tabs[7]:  page_trade_analyzer(seasons, players)
    with tabs[8]:  page_immaculate_grid(seasons, players)
    with tabs[9]:  page_tools(seasons, players)
    with tabs[10]: page_league_stats()
    with tabs[11]: page_wiki()

if __name__ == "__main__":
    main()
