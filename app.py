import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# ─── Config ──────────────────────────────────────────────────────────────────
LEAGUE_ID = "1312122172180824064"
BASE_URL = "https://api.sleeper.app/v1"

st.set_page_config(
    page_title="CRC Dynasty Dashboard",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.metric-card {
    background: #1e1e2e;
    border-radius: 12px;
    padding: 16px 20px;
    border: 1px solid #313244;
    text-align: center;
}
.metric-card .label { color: #a6adc8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
.metric-card .value { color: #cdd6f4; font-size: 1.6rem; font-weight: 700; margin-top: 4px; }
.metric-card .sub   { color: #6c7086; font-size: 0.75rem; margin-top: 2px; }
.champ-banner {
    background: linear-gradient(135deg, #f9e2af22, #fab38722);
    border: 1px solid #f9e2af55;
    border-radius: 12px;
    padding: 16px 24px;
    margin-bottom: 16px;
}
.pos-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 700;
    color: white;
}
.QB  { background: #f38ba8; }
.RB  { background: #a6e3a1; color: #1e1e2e !important; }
.WR  { background: #89b4fa; }
.TE  { background: #fab387; color: #1e1e2e !important; }
.K   { background: #a6adc8; color: #1e1e2e !important; }
.DEF { background: #cba6f7; }
.section-header {
    font-size: 1.2rem;
    font-weight: 600;
    color: #cdd6f4;
    border-bottom: 2px solid #313244;
    padding-bottom: 6px;
    margin: 20px 0 12px 0;
}
</style>
""", unsafe_allow_html=True)

# ─── API layer ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def api_get(path):
    r = requests.get(f"{BASE_URL}{path}", timeout=15)
    r.raise_for_status()
    return r.json()

def get_league(lid):            return api_get(f"/league/{lid}")
def get_rosters(lid):           return api_get(f"/league/{lid}/rosters")
def get_users(lid):             return api_get(f"/league/{lid}/users")
def get_matchups(lid, week):    return api_get(f"/league/{lid}/matchups/{week}")
def get_transactions(lid, week): return api_get(f"/league/{lid}/transactions/{week}")
def get_drafts(lid):            return api_get(f"/league/{lid}/drafts")
def get_draft_picks(did):       return api_get(f"/draft/{did}/picks")
def get_traded_picks(lid):      return api_get(f"/league/{lid}/traded_picks")

@st.cache_data(ttl=86400 * 3, show_spinner="Downloading player database…")
def get_players():
    return requests.get(f"{BASE_URL}/players/nfl", timeout=60).json()

@st.cache_data(ttl=600)
def get_season_chain(root_id):
    """Returns list of league dicts from newest → oldest."""
    seasons, lid = [], root_id
    while lid and lid != "0":
        try:
            lg = get_league(lid)
            seasons.append(lg)
            lid = lg.get("previous_league_id") or "0"
        except Exception:
            break
    return seasons

# ─── Helpers ─────────────────────────────────────────────────────────────────

def build_team_map(users, rosters):
    u_map = {u["user_id"]: u for u in users}
    teams = {}
    for r in rosters:
        uid = r.get("owner_id")
        u = u_map.get(uid, {})
        meta = u.get("metadata") or {}
        teams[r["roster_id"]] = {
            "display_name": u.get("display_name", "Unknown"),
            "team_name":    meta.get("team_name") or u.get("display_name", "Unknown"),
            "user_id":      uid,
            "avatar":       u.get("avatar"),
            "roster":       r,
        }
    return teams

def player_info(pid, players):
    p = players.get(str(pid), {})
    fn = p.get("first_name", "")
    ln = p.get("last_name", "")
    name = f"{fn} {ln}".strip() or f"Player {pid}"
    pos  = p.get("fantasy_positions", [p.get("position", "?")])[0] if p else "?"
    team = p.get("team") or "FA"
    age  = p.get("age") or "?"
    return name, pos, team, age

def fpts(settings, key="fpts"):
    return settings.get(key, 0) + settings.get(f"{key}_decimal", 0) / 100

def pos_color(pos):
    colors = {"QB": "#f38ba8", "RB": "#a6e3a1", "WR": "#89b4fa",
              "TE": "#fab387", "K": "#a6adc8", "DEF": "#cba6f7"}
    return colors.get(pos, "#6c7086")

# ─── Pages ────────────────────────────────────────────────────────────────────

def page_home(seasons, players):
    st.title("🏈 CRC Dynasty League")

    completed = [s for s in seasons if s["status"] == "complete"]
    current   = seasons[0]  # newest

    # Champion banner
    if completed:
        champ_lg   = completed[0]
        champ_rid  = champ_lg.get("metadata", {}).get("latest_league_winner_roster_id")
        champ_users = get_users(champ_lg["league_id"])
        champ_rost  = get_rosters(champ_lg["league_id"])
        champ_teams = build_team_map(champ_users, champ_rost)
        champ       = champ_teams.get(int(champ_rid), {}) if champ_rid else {}
        if champ:
            st.markdown(f"""
            <div class="champ-banner">
                <span style="font-size:1.5rem">🏆</span>
                <strong style="font-size:1.1rem; color:#f9e2af"> {champ_lg['season']} Champion:</strong>
                <span style="font-size:1.1rem; color:#cdd6f4"> {champ['team_name']}</span>
                <span style="color:#a6adc8"> — {champ['display_name']}</span>
            </div>
            """, unsafe_allow_html=True)

    # Season overview cards
    cols = st.columns(4)
    with cols[0]:
        st.markdown(f"""<div class="metric-card">
            <div class="label">Current Season</div>
            <div class="value">{current['season']}</div>
            <div class="sub">{current['status'].replace('_', ' ').title()}</div>
        </div>""", unsafe_allow_html=True)
    with cols[1]:
        st.markdown(f"""<div class="metric-card">
            <div class="label">Total Seasons</div>
            <div class="value">{len(seasons)}</div>
            <div class="sub">Since {seasons[-1]['season']}</div>
        </div>""", unsafe_allow_html=True)
    with cols[2]:
        st.markdown(f"""<div class="metric-card">
            <div class="label">Teams</div>
            <div class="value">{current['total_rosters']}</div>
            <div class="sub">Dynasty PPR</div>
        </div>""", unsafe_allow_html=True)
    with cols[3]:
        roster_pos = current.get("roster_positions", [])
        starters = [p for p in roster_pos if p not in ("BN", "IR", "TAXI")]
        st.markdown(f"""<div class="metric-card">
            <div class="label">Lineup Spots</div>
            <div class="value">{len(starters)}</div>
            <div class="sub">{len(roster_pos)} total roster spots</div>
        </div>""", unsafe_allow_html=True)

    # All-time records table
    st.markdown('<div class="section-header">All-Time Records</div>', unsafe_allow_html=True)
    rows = []
    for lg in completed:
        lg_rost  = get_rosters(lg["league_id"])
        lg_users = get_users(lg["league_id"])
        lg_teams = build_team_map(lg_users, lg_rost)
        w_rid    = lg.get("metadata", {}).get("latest_league_winner_roster_id")
        for r in lg_rost:
            rid = r["roster_id"]
            t   = lg_teams.get(rid, {})
            s   = r["settings"]
            rows.append({
                "Season":   lg["season"],
                "Manager":  t.get("display_name", "?"),
                "Team":     t.get("team_name", "?"),
                "W":        s.get("wins", 0),
                "L":        s.get("losses", 0),
                "PF":       round(fpts(s), 2),
                "PA":       round(fpts(s, "fpts_against"), 2),
                "Champ":    "🏆" if str(rid) == str(w_rid) else "",
            })

    if rows:
        df = pd.DataFrame(rows)
        agg = df.groupby("Manager").agg(
            Seasons      = ("Season", "count"),
            Wins         = ("W", "sum"),
            Losses       = ("L", "sum"),
            Total_PF     = ("PF", "sum"),
            Championships= ("Champ", lambda x: (x == "🏆").sum()),
        ).reset_index()
        agg["Win%"] = (agg["Wins"] / (agg["Wins"] + agg["Losses"]) * 100).round(1)
        agg["Total_PF"] = agg["Total_PF"].round(1)
        agg = agg.sort_values(["Championships", "Win%"], ascending=False).reset_index(drop=True)
        agg.index += 1

        col1, col2 = st.columns([2, 3])
        with col1:
            st.dataframe(
                agg.rename(columns={"Total_PF": "Total PF", "Championships": "🏆"}),
                use_container_width=True,
            )
        with col2:
            fig = px.bar(
                agg, x="Manager", y=["Wins", "Losses"],
                title="All-Time W/L by Manager",
                color_discrete_map={"Wins": "#a6e3a1", "Losses": "#f38ba8"},
                barmode="stack",
            )
            fig.update_layout(height=320, margin=dict(l=0, r=0, t=40, b=0),
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#cdd6f4", legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)

        # Season-by-season PF chart
        pivot = df.pivot_table(index="Season", columns="Manager", values="PF", aggfunc="sum")
        fig2 = px.line(pivot.reset_index().melt(id_vars="Season", var_name="Manager", value_name="PF"),
                       x="Season", y="PF", color="Manager",
                       title="Points For by Season", markers=True)
        fig2.update_layout(height=320, margin=dict(l=0, r=0, t=40, b=0),
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font_color="#cdd6f4")
        st.plotly_chart(fig2, use_container_width=True)


def page_standings(seasons, players):
    st.title("📊 Standings")

    completed = [s for s in seasons if s["status"] == "complete"]
    options   = {lg["season"]: lg["league_id"] for lg in completed}
    if not options:
        st.info("No completed seasons yet.")
        return

    sel = st.selectbox("Season", list(options.keys()))
    lid = options[sel]
    lg  = get_league(lid)

    rosters = get_rosters(lid)
    users   = get_users(lid)
    teams   = build_team_map(users, rosters)
    w_rid   = lg.get("metadata", {}).get("latest_league_winner_roster_id")

    rows = []
    for r in rosters:
        rid = r["roster_id"]
        t   = teams.get(rid, {})
        s   = r["settings"]
        pf  = fpts(s)
        pa  = fpts(s, "fpts_against")
        pp  = fpts(s, "ppts")
        rows.append({
            "#":       rid,
            "Team":    t.get("team_name", "?"),
            "Manager": t.get("display_name", "?"),
            "W":       s.get("wins", 0),
            "L":       s.get("losses", 0),
            "PF":      round(pf, 2),
            "PA":      round(pa, 2),
            "Max PF":  round(pp, 2),
            "Eff%":    round(pf / pp * 100, 1) if pp else 0,
            "":        "🏆" if str(rid) == str(w_rid) else "",
        })

    df = pd.DataFrame(rows).sort_values(["W", "PF"], ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))
    df = df.drop("#", axis=1)

    col1, col2 = st.columns([3, 2])
    with col1:
        st.dataframe(df, use_container_width=True, height=340)
    with col2:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df["PF"], y=df["Team"], orientation="h",
            name="PF", marker_color="#89b4fa",
        ))
        fig.add_trace(go.Bar(
            x=df["Max PF"], y=df["Team"], orientation="h",
            name="Max PF", marker_color="#313244",
        ))
        fig.update_layout(
            title="Points For vs Max PF", barmode="overlay",
            height=340, margin=dict(l=0, r=0, t=40, b=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#cdd6f4",
        )
        st.plotly_chart(fig, use_container_width=True)

    # Weekly score distribution
    st.markdown('<div class="section-header">Weekly Score Distribution</div>', unsafe_allow_html=True)
    playoff_start = lg["settings"].get("playoff_week_start", 14)
    last_week     = lg["settings"].get("last_scored_leg", 13)
    reg_weeks     = range(1, min(playoff_start, last_week + 1))

    all_scores = []
    prog = st.progress(0, text="Loading weekly matchups…")
    for i, w in enumerate(reg_weeks):
        try:
            mups = get_matchups(lid, w)
            for m in mups:
                if m.get("points") is not None:
                    rid = m["roster_id"]
                    t   = teams.get(rid, {})
                    all_scores.append({
                        "Week": w,
                        "Team": t.get("team_name", str(rid)),
                        "Manager": t.get("display_name", "?"),
                        "Score": m["points"],
                    })
        except Exception:
            pass
        prog.progress((i + 1) / len(reg_weeks))
    prog.empty()

    if all_scores:
        sc_df = pd.DataFrame(all_scores)
        fig3 = px.box(
            sc_df, x="Manager", y="Score",
            title="Score Distribution (Regular Season)",
            color="Manager",
        )
        fig3.update_layout(
            height=380, margin=dict(l=0, r=0, t=40, b=60),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#cdd6f4", showlegend=False,
        )
        st.plotly_chart(fig3, use_container_width=True)

        fig4 = px.line(
            sc_df, x="Week", y="Score", color="Manager",
            title="Scores by Week", markers=True,
        )
        fig4.update_layout(
            height=380, margin=dict(l=0, r=0, t=40, b=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#cdd6f4",
        )
        st.plotly_chart(fig4, use_container_width=True)


def page_teams(seasons, players):
    st.title("🏟️ Team Rosters")

    # Pick season (default current)
    season_opts = {lg["season"]: lg["league_id"] for lg in seasons}
    sel_season  = st.selectbox("Season", list(season_opts.keys()))
    lid         = season_opts[sel_season]

    rosters = get_rosters(lid)
    users   = get_users(lid)
    teams   = build_team_map(users, rosters)

    team_names  = {rid: t["team_name"] for rid, t in teams.items()}
    sel_rid     = st.selectbox("Team", list(team_names.keys()),
                               format_func=lambda x: f"{team_names[x]} ({teams[x]['display_name']})")
    t    = teams[sel_rid]
    r    = t["roster"]
    meta = r.get("metadata") or {}

    col1, col2, col3 = st.columns(3)
    s = r["settings"]
    with col1:
        st.markdown(f"""<div class="metric-card">
            <div class="label">Record</div>
            <div class="value">{s.get('wins',0)}-{s.get('losses',0)}</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        pf_val = fpts(s)
        st.markdown(f"""<div class="metric-card">
            <div class="label">Points For</div>
            <div class="value">{round(pf_val,1)}</div>
        </div>""", unsafe_allow_html=True)
    with col3:
        pa_val = fpts(s, "fpts_against")
        st.markdown(f"""<div class="metric-card">
            <div class="label">Points Against</div>
            <div class="value">{round(pa_val,1)}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    starters  = set(r.get("starters") or [])
    reserve   = set(r.get("reserve") or [])
    taxi      = set(r.get("taxi") or [])
    all_pids  = r.get("players") or []

    def roster_section(title, pids, color):
        if not pids:
            return
        st.markdown(f'<div class="section-header" style="color:{color}">{title}</div>',
                    unsafe_allow_html=True)
        rows = []
        for pid in pids:
            name, pos, team, age = player_info(pid, players)
            nick = meta.get(f"p_nick_{pid}", "")
            rows.append({"Player": name, "Pos": pos, "NFL Team": team,
                         "Age": age, "Nickname": nick})
        df = pd.DataFrame(rows).sort_values(["Pos", "Player"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    bench = [p for p in all_pids if p not in starters and p not in reserve and p not in taxi]

    roster_section("▶ Starters", list(starters), "#a6e3a1")
    roster_section("🪑 Bench",   bench,           "#89b4fa")
    roster_section("🚑 IR / Reserve", list(reserve), "#f38ba8")
    roster_section("🚕 Taxi Squad", list(taxi),    "#f9e2af")

    # Age analysis (dynasty-specific)
    st.markdown('<div class="section-header">Dynasty Age Analysis</div>', unsafe_allow_html=True)
    age_rows = []
    for pid in all_pids:
        name, pos, team, age = player_info(pid, players)
        if isinstance(age, (int, float)):
            age_rows.append({"Player": name, "Pos": pos, "Age": int(age),
                             "Type": "Starter" if pid in starters else
                                     "IR" if pid in reserve else
                                     "Taxi" if pid in taxi else "Bench"})
    if age_rows:
        age_df = pd.DataFrame(age_rows)
        avg_age = age_df["Age"].mean()
        starter_avg = age_df[age_df["Type"] == "Starter"]["Age"].mean()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Avg Roster Age", f"{avg_age:.1f}")
        with col2:
            st.metric("Avg Starter Age", f"{starter_avg:.1f}")

        fig = px.histogram(age_df, x="Age", color="Pos", nbins=15,
                           title="Roster Age Distribution",
                           color_discrete_sequence=px.colors.qualitative.Pastel)
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=40, b=0),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font_color="#cdd6f4")
        st.plotly_chart(fig, use_container_width=True)


def page_matchups(seasons, players):
    st.title("📅 Matchups")

    completed = [s for s in seasons if s["status"] == "complete"]
    if not completed:
        st.info("No completed seasons available.")
        return

    season_opts = {lg["season"]: lg["league_id"] for lg in completed}
    sel_season  = st.selectbox("Season", list(season_opts.keys()))
    lid         = season_opts[sel_season]
    lg          = get_league(lid)
    last_week   = lg["settings"].get("last_scored_leg", 17)
    pw_start    = lg["settings"].get("playoff_week_start", 14)

    rosters = get_rosters(lid)
    users   = get_users(lid)
    teams   = build_team_map(users, rosters)

    sel_week = st.slider("Week", 1, last_week, 1)
    matchups  = get_matchups(lid, sel_week)

    # Group by matchup_id
    groups = {}
    for m in matchups:
        mid = m.get("matchup_id")
        if mid not in groups:
            groups[mid] = []
        groups[mid].append(m)

    label = "🏆 Playoff" if sel_week >= pw_start else "📆 Regular Season"
    st.markdown(f"**Week {sel_week}** — {label}")

    for mid, pair in sorted(groups.items()):
        if len(pair) < 2:
            continue
        a, b = sorted(pair, key=lambda x: x.get("points", 0) or 0, reverse=True)
        ta = teams.get(a["roster_id"], {})
        tb = teams.get(b["roster_id"], {})
        pa = a.get("points") or 0
        pb = b.get("points") or 0

        col1, mid_col, col2 = st.columns([5, 2, 5])
        with col1:
            win = pa > pb
            color = "#a6e3a1" if win else "#f38ba8"
            st.markdown(f"""
            <div style="background:#1e1e2e;border:1px solid #313244;border-radius:10px;padding:14px 18px;">
                <div style="font-size:0.8rem;color:#a6adc8">{ta.get('display_name','')}</div>
                <div style="font-size:1.1rem;font-weight:600;color:#cdd6f4">{ta.get('team_name','?')}</div>
                <div style="font-size:2rem;font-weight:800;color:{color}">{pa:.2f}</div>
            </div>""", unsafe_allow_html=True)
        with mid_col:
            st.markdown("<div style='text-align:center;padding-top:30px;color:#6c7086;font-size:1.2rem'>vs</div>",
                        unsafe_allow_html=True)
        with col2:
            win = pb > pa
            color = "#a6e3a1" if win else "#f38ba8"
            st.markdown(f"""
            <div style="background:#1e1e2e;border:1px solid #313244;border-radius:10px;padding:14px 18px;text-align:right;">
                <div style="font-size:0.8rem;color:#a6adc8">{tb.get('display_name','')}</div>
                <div style="font-size:1.1rem;font-weight:600;color:#cdd6f4">{tb.get('team_name','?')}</div>
                <div style="font-size:2rem;font-weight:800;color:{color}">{pb:.2f}</div>
            </div>""", unsafe_allow_html=True)
        st.markdown("")


def page_transactions(seasons, players):
    st.title("💱 Transactions")

    completed = [s for s in seasons if s["status"] == "complete"]
    season_opts = {lg["season"]: lg["league_id"] for lg in completed}
    if not season_opts:
        st.info("No completed seasons available.")
        return

    sel_season = st.selectbox("Season", list(season_opts.keys()))
    lid = season_opts[sel_season]
    lg  = get_league(lid)
    last_week = lg["settings"].get("last_scored_leg", 17)

    rosters = get_rosters(lid)
    users   = get_users(lid)
    teams   = build_team_map(users, rosters)

    txn_type = st.selectbox("Type", ["All", "Trade", "Waiver", "Free Agent"])

    # Load all transactions
    all_txns = []
    prog = st.progress(0, text="Loading transactions…")
    for i, w in enumerate(range(1, last_week + 1)):
        try:
            txns = get_transactions(lid, w)
            for t in txns:
                t["_week"] = w
            all_txns.extend(txns)
        except Exception:
            pass
        prog.progress((i + 1) / last_week)
    prog.empty()

    # Filter
    type_map = {"Trade": "trade", "Waiver": "waiver", "Free Agent": "free_agent"}
    if txn_type != "All":
        all_txns = [t for t in all_txns if t.get("type") == type_map[txn_type]]

    all_txns.sort(key=lambda x: x.get("created", 0), reverse=True)

    trades  = [t for t in all_txns if t.get("type") == "trade"]
    waivers = [t for t in all_txns if t.get("type") in ("waiver", "free_agent")]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""<div class="metric-card">
            <div class="label">Total Transactions</div>
            <div class="value">{len(all_txns)}</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="metric-card">
            <div class="label">Trades</div>
            <div class="value">{len(trades)}</div>
        </div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""<div class="metric-card">
            <div class="label">Waiver / FA Moves</div>
            <div class="value">{len(waivers)}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    if txn_type in ("All", "Trade"):
        st.markdown('<div class="section-header">Trades</div>', unsafe_allow_html=True)
        for txn in trades:
            if txn.get("status") != "complete":
                continue
            rids    = txn.get("roster_ids", [])
            adds    = txn.get("adds") or {}
            drops   = txn.get("drops") or {}
            picks   = txn.get("draft_picks") or []
            ts      = txn.get("created", 0)
            dt      = datetime.fromtimestamp(ts / 1000).strftime("%b %d") if ts else "?"
            week    = txn.get("_week", "?")

            with st.expander(f"Week {week} — {' ↔ '.join([teams.get(r, {}).get('team_name', str(r)) for r in rids])}  ({dt})"):
                side_cols = st.columns(len(rids)) if len(rids) > 0 else [st]
                for i, rid in enumerate(rids):
                    tname = teams.get(rid, {}).get("team_name", str(rid))
                    with side_cols[i]:
                        st.markdown(f"**{tname}** receives:")
                        # players this roster receives = added to this roster
                        received = [pid for pid, r in adds.items() if r == rid]
                        lost     = [pid for pid, r in drops.items() if r == rid]
                        # picks this roster receives
                        recv_picks = [p for p in picks if p.get("owner_id") == rid]

                        for pid in received:
                            name, pos, team, _ = player_info(pid, players)
                            st.markdown(f"<span class='pos-badge {pos}'>{pos}</span> {name} ({team})",
                                        unsafe_allow_html=True)
                        for pk in recv_picks:
                            st.markdown(f"📋 {pk.get('season')} Rd {pk.get('round')} pick")

    if txn_type in ("All", "Waiver", "Free Agent"):
        st.markdown('<div class="section-header">Waiver / FA Moves</div>', unsafe_allow_html=True)
        rows = []
        for txn in waivers:
            if txn.get("status") != "complete":
                continue
            rids  = txn.get("roster_ids", [])
            adds  = txn.get("adds") or {}
            drops = txn.get("drops") or {}
            ts    = txn.get("created", 0)
            dt    = datetime.fromtimestamp(ts / 1000).strftime("%b %d") if ts else "?"
            week  = txn.get("_week", "?")
            bid   = (txn.get("settings") or {}).get("waiver_bid", 0)
            tname = teams.get(rids[0], {}).get("team_name", str(rids[0])) if rids else "?"

            for pid, rid in adds.items():
                name, pos, team, _ = player_info(pid, players)
                rows.append({
                    "Week": week, "Date": dt, "Team": tname,
                    "Add": name, "Pos": pos, "NFL": team,
                    "FAAB": f"${bid}" if bid else "FA",
                })

        if rows:
            w_df = pd.DataFrame(rows)
            st.dataframe(w_df, use_container_width=True, hide_index=True)


def page_draft(seasons, players):
    st.title("📜 Draft History")

    all_seasons = seasons  # including current
    season_opts = {lg["season"]: lg["league_id"] for lg in all_seasons}
    sel_season  = st.selectbox("Season", list(season_opts.keys()))
    lid         = season_opts[sel_season]

    drafts = get_drafts(lid)
    if not drafts:
        st.info("No drafts found for this season.")
        return

    rosters = get_rosters(lid)
    users   = get_users(lid)
    teams   = build_team_map(users, rosters)

    draft   = drafts[0]  # usually one draft per season
    status  = draft.get("status", "unknown")
    rounds  = draft.get("settings", {}).get("rounds", 4)

    st.markdown(f"**Draft Type:** {draft.get('type','?').replace('_',' ').title()}  |  "
                f"**Rounds:** {rounds}  |  **Status:** {status.title()}")

    if status == "pre_draft":
        st.info("This draft hasn't started yet.")
        # Show draft order
        order = draft.get("draft_order") or {}
        if order:
            st.markdown('<div class="section-header">Draft Order</div>', unsafe_allow_html=True)
            order_rows = []
            for uid, slot in sorted(order.items(), key=lambda x: x[1]):
                mgr = next((u.get("display_name","?") for u in users if u["user_id"] == uid), "?")
                team_obj = next((t for t in teams.values() if t["user_id"] == uid), {})
                order_rows.append({"Slot": slot, "Manager": mgr,
                                   "Team": team_obj.get("team_name","?")})
            st.dataframe(pd.DataFrame(order_rows).sort_values("Slot"),
                         use_container_width=True, hide_index=True)
        return

    with st.spinner("Loading draft picks…"):
        picks = get_draft_picks(draft["draft_id"])

    if not picks:
        st.info("No picks available yet.")
        return

    rows = []
    for pk in picks:
        pid   = pk.get("player_id")
        name, pos, team, age = player_info(pid, players)
        rid   = pk.get("roster_id") or pk.get("picked_by")
        tname = teams.get(rid, {}).get("team_name", str(rid)) if rid else "?"
        rows.append({
            "Pick":    pk.get("pick_no"),
            "Rd":      pk.get("round"),
            "Slot":    pk.get("draft_slot"),
            "Player":  name,
            "Pos":     pos,
            "NFL":     team,
            "Age":     age,
            "Team":    tname,
        })

    df = pd.DataFrame(rows).sort_values("Pick")

    # Filter by position
    positions = ["All"] + sorted(df["Pos"].unique().tolist())
    sel_pos   = st.selectbox("Filter by Position", positions)
    if sel_pos != "All":
        df = df[df["Pos"] == sel_pos]

    st.dataframe(df, use_container_width=True, hide_index=True)

    # Pick distribution by position
    full_df = pd.DataFrame(rows)
    pos_counts = full_df.groupby("Pos").size().reset_index(name="Picks")
    fig = px.pie(pos_counts, names="Pos", values="Picks",
                 title="Draft Pick Distribution by Position",
                 color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(height=320, paper_bgcolor="rgba(0,0,0,0)", font_color="#cdd6f4")
    st.plotly_chart(fig, use_container_width=True)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    with st.spinner("Loading league data…"):
        seasons = get_season_chain(LEAGUE_ID)
        players = get_players()

    tabs = st.tabs(["🏠 Home", "📊 Standings", "🏟️ Teams", "📅 Matchups",
                    "💱 Transactions", "📜 Draft"])

    with tabs[0]: page_home(seasons, players)
    with tabs[1]: page_standings(seasons, players)
    with tabs[2]: page_teams(seasons, players)
    with tabs[3]: page_matchups(seasons, players)
    with tabs[4]: page_transactions(seasons, players)
    with tabs[5]: page_draft(seasons, players)


if __name__ == "__main__":
    main()
