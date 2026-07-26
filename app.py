import streamlit as st
import math
import pandas as pd
import random
import io
from supabase import create_client, Client

st.set_page_config(page_title="Quant Betting Engine", page_icon="📈", layout="wide")

# --- SUPABASE DATENBANK ANBINDUNG ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def load_journal():
    try:
        response = supabase.table("app_state").select("journal_data").eq("id", 1).execute()
        if response.data: return response.data[0]["journal_data"]
        return []
    except: return []

def save_journal(journal_data):
    try:
        supabase.table("app_state").update({"journal_data": journal_data}).eq("id", 1).execute()
    except Exception as e:
        st.sidebar.error("Fehler beim Speichern in der DB!")

if 'journal' not in st.session_state:
    loaded_data = load_journal()
    for bet in loaded_data:
        if "Liga" not in bet: bet["Liga"] = "Unbekannt"
        if "Closing Quote" not in bet: bet["Closing Quote"] = bet.get("Quote", 0.0)
    st.session_state.journal = loaded_data

# --- MATHEMATIK & CACHING ---
@st.cache_data
def zip_poisson(k, lambd, zip_factor):
    p = (lambd**k * math.exp(-lambd)) / math.factorial(k)
    if k == 0: return zip_factor + (1 - zip_factor) * p
    else: return (1 - zip_factor) * p

@st.cache_data
def dixon_coles_adjustment(home_goals, away_goals, lambd, mu, rho):
    if home_goals == 0 and away_goals == 0: return 1 - (lambd * mu * rho)
    elif home_goals == 1 and away_goals == 0: return 1 + (mu * rho)
    elif home_goals == 0 and away_goals == 1: return 1 + (lambd * rho)
    elif home_goals == 1 and away_goals == 1: return 1 - rho
    else: return 1.0

@st.cache_data
def calculate_match_probabilities(xg_home, xg_away, rho, zip_factor, current_minute=0, score_home=0, score_away=0, red_home=False, red_away=False):
    prob_1, prob_x, prob_2, prob_over_25, prob_btts = 0.0, 0.0, 0.0, 0.0, 0.0
    p_m_plus2, p_m_plus1, p_m_0, p_m_minus1, p_m_minus2 = 0.0, 0.0, 0.0, 0.0, 0.0
    
    time_factor = max((90 - current_minute) / 90.0, 0.001)
    rem_xg_home, rem_xg_away = xg_home * time_factor, xg_away * time_factor

    if red_home and not red_away:
        rem_xg_home *= 0.60; rem_xg_away *= 1.35
    elif red_away and not red_home:
        rem_xg_away *= 0.60; rem_xg_home *= 1.35
    elif red_home and red_away:
        rem_xg_home *= 1.10; rem_xg_away *= 1.10

    for added_home in range(8):
        for added_away in range(8):
            prob = zip_poisson(added_home, rem_xg_home, zip_factor) * zip_poisson(added_away, rem_xg_away, zip_factor)
            prob *= dixon_coles_adjustment(added_home, added_away, rem_xg_home, rem_xg_away, rho)
            if prob < 0: prob = 0
            
            final_home, final_away = score_home + added_home, score_away + added_away
            margin = final_home - final_away
            
            if margin >= 2: p_m_plus2 += prob
            elif margin == 1: p_m_plus1 += prob
            elif margin == 0: p_m_0 += prob
            elif margin == -1: p_m_minus1 += prob
            elif margin <= -2: p_m_minus2 += prob
            
            if final_home > final_away: prob_1 += prob
            elif final_home == final_away: prob_x += prob
            else: prob_2 += prob
                
            if (final_home + final_away) > 2.5: prob_over_25 += prob
            if final_home > 0 and final_away > 0: prob_btts += prob
                
    total_prob = prob_1 + prob_x + prob_2
    p1, px, p2 = prob_1 / total_prob, prob_x / total_prob, prob_2 / total_prob
    
    m_total = p_m_plus2 + p_m_plus1 + p_m_0 + p_m_minus1 + p_m_minus2
    if m_total > 0:
        p_m_plus2 /= m_total; p_m_plus1 /= m_total; p_m_0 /= m_total; p_m_minus1 /= m_total; p_m_minus2 /= m_total
    
    return {
        "1": p1, "X": px, "2": p2, "Over25": prob_over_25, "BTTS": prob_btts,
        "margins": {"+2": p_m_plus2, "+1": p_m_plus1, "0": p_m_0, "-1": p_m_minus1, "-2": p_m_minus2}
    }

def get_ah_odds(m2, m1, m0, mm1, mm2):
    def calc(win, h_win, push, h_loss, loss):
        d = win + 0.5 * h_win
        if d <= 0: return 0.0
        return round((1 - push - 0.5 * h_win - 0.5 * h_loss) / d, 2)
    return {
        "H": [
            calc(m2, 0, 0, 0, m1+m0+mm1+mm2), calc(m2, 0, m1, 0, m0+mm1+mm2), calc(m2, m1, 0, 0, m0+mm1+mm2),
            calc(m2+m1, 0, 0, 0, m0+mm1+mm2), calc(m2+m1, 0, 0, m0, mm1+mm2), calc(m2+m1, 0, m0, 0, mm1+mm2),
            calc(m2+m1, m0, 0, 0, mm1+mm2), calc(m2+m1+m0, 0, 0, 0, mm1+mm2), calc(m2+m1+m0, 0, 0, mm1, mm2),
            calc(m2+m1+m0, 0, mm1, 0, mm2), calc(m2+m1+m0+mm1, 0, 0, 0, mm2)
        ],
        "A": [
            calc(mm2+mm1+m0+m1, 0, 0, 0, m2), calc(mm2+mm1+m0, 0, m1, 0, m2), calc(mm2+mm1+m0, 0, 0, m1, m2),
            calc(mm2+mm1+m0, 0, 0, 0, m1+m2), calc(mm2+mm1, m0, 0, 0, m1+m2), calc(mm2+mm1, 0, m0, 0, m1+m2),
            calc(mm2+mm1, 0, 0, m0, m1+m2), calc(mm2+mm1, 0, 0, 0, m0+m1+m2), calc(mm2, mm1, 0, 0, m0+m1+m2),
            calc(mm2, 0, mm1, 0, m0+m1+m2), calc(mm2, 0, 0, 0, mm1+m0+m1+m2)
        ]
    }

def calculate_ev(prob, odds): return (prob * odds) - 1
def calculate_kelly(prob, odds, fraction=0.25):
    k = (prob * (odds - 1) - (1 - prob)) / (odds - 1)
    return k * fraction if k > 0 else 0
def format_odds(prob): return round(1 / prob, 2) if prob > 0 else 0.0

@st.cache_data
def get_true_probabilities(odds_1, odds_x, odds_2):
    i1, ix, i2 = 1 / odds_1, 1 / odds_x, 1 / odds_2
    vig = i1 + ix + i2
    if vig <= 1.0: return i1/vig, ix/vig, i2/vig, vig
    low, high = 1.0, 10.0
    for _ in range(50):
        k = (low + high) / 2
        if (i1**k + ix**k + i2**k) > 1.0: low = k
        else: high = k
    return i1**k, ix**k, i2**k, vig

@st.cache_data
def reverse_engineer_odds(true_p1, true_px, true_p2, rho, zip_factor):
    best_diff, best_xg_h, best_xg_a = 999.0, 1.0, 1.0
    for h in range(1, 41):
        for a in range(1, 41):
            xgh, xga = h / 10.0, a / 10.0
            probs = calculate_match_probabilities(xgh, xga, rho, zip_factor, 0, 0, 0)
            diff = abs(probs["1"] - true_p1) + abs(probs["X"] - true_px) + abs(probs["2"] - true_p2)
            if diff < best_diff: best_diff, best_xg_h, best_xg_a = diff, xgh, xga
    return best_xg_h, best_xg_a

def map_raw_columns(df):
    df.columns = [str(c).strip().lower() for c in df.columns]
    mapping = {
        'HomeTeam': ['hometeam', 'home_team_name', 'home team', 'team1', 'home'],
        'AwayTeam': ['awayteam', 'away_team_name', 'away team', 'team2', 'away'],
        'Home_xG': ['home_xg', 'team_a_xg', 'homexg', 'xg_home', 'expected_goals_home'],
        'Away_xG': ['away_xg', 'team_b_xg', 'awayxg', 'xg_away', 'expected_goals_away'],
        'Odds_1': ['odds_1', 'odds_ft_1', 'home_odds', 'odds1', '1'],
        'Odds_X': ['odds_x', 'odds_ft_x', 'draw_odds', 'oddsx', 'x', 'draw'],
        'Odds_2': ['odds_2', 'odds_ft_2', 'away_odds', 'odds2', '2'],
        'Home_Scored': ['home_scored', 'home_team_goal_count', 'home_goals_avg'],
        'Home_Conceded': ['home_conceded', 'home_team_goals_conceded', 'home_conceded_avg'],
        'Away_Scored': ['away_scored', 'away_team_goal_count', 'away_goals_avg'],
        'Away_Conceded': ['away_conceded', 'away_team_goals_conceded', 'away_conceded_avg'],
        'League_Avg': ['league_avg', 'average_goals_per_match']
    }
    
    new_df = pd.DataFrame()
    found_cols = []
    for std_col, aliases in mapping.items():
        for alias in aliases:
            if alias in df.columns:
                new_df[std_col] = df[alias]
                found_cols.append(std_col)
                break
    return new_df, found_cols

# --- APP UI ---
st.title("📈 Pro Quant Engine")

with st.expander("⚙️ Kontrollzentrum (Bankroll & Risiko)", expanded=False):
    st.markdown("**1. Bankroll & Limit**")
    c_k1, c_k2, c_k3 = st.columns(3)
    with c_k1: start_bankroll = st.number_input("Initiale Bankroll (€)", min_value=1.0, value=10.0, step=0.5)
    with c_k2: min_bet = st.number_input("Mindest-Bet (€)", min_value=0.1, value=0.5, step=0.1)
    with c_k3: max_risk_pct = st.number_input("Max. Risiko (%)", min_value=1.0, max_value=15.0, value=5.0, step=0.5)

    st.markdown("**2. Kelly & Diversifikation**")
    c_k4, c_k5 = st.columns(2)
    with c_k4: kelly_fraction = st.select_slider("Kelly-Faktor", options=[0.125, 0.25, 0.5, 1.0], value=0.25, format_func=lambda x: f"{int(1/x)}/1 Kelly")
    with c_k5: parallel_bets = st.number_input("Parallele Spiele (Diversifikation)", min_value=1, max_value=20, value=1, step=1)

    st.markdown("**3. Engine Tuning**")
    c_k6, c_k7 = st.columns(2)
    with c_k6: zip_factor = st.slider("ZIP-Faktor (0:0 Boost)", 0.0, 0.20, 0.05, 0.01)
    with c_k7: rho = st.slider("Dixon-Coles Faktor", -0.30, 0.0, -0.15, 0.01)

current_bankroll, exposure = start_bankroll, 0.0
for bet in st.session_state.journal:
    current_bankroll -= bet['Einsatz']
    if bet['Status'] == 'Gewonnen': current_bankroll += bet['Einsatz'] * bet['Quote']
    if bet['Status'] == 'Offen': exposure += bet['Einsatz']

tab_engine, tab_bulk, tab_journal, tab_manual = st.tabs(["⚙️ Engine & Scanner", "📂 Bulk-Scanner", "📖 Portfolio", "📚 Handbuch"])

# --- TAB 1: ENGINE & SCANNER ---
with tab_engine:
    st.markdown("### 1. Daten-Eingabe (Dein Modell)")
    data_mode = st.radio("Wie möchtest du die Team-Stärke berechnen?", ["Direkte xG-Werte eingeben", "AS/DS Rechner (Kleine Ligen)"], horizontal=True)
    
    if data_mode == "Direkte xG-Werte eingeben":
        c_xg1, c_xg2 = st.columns(2)
        with c_xg1: xg_home = st.number_input("Erwartete Tore Heim ($xG$)", min_value=0.1, max_value=5.0, value=1.5, step=0.1)
        with c_xg2: xg_away = st.number_input("Erwartete Tore Auswärts ($xG$)", min_value=0.1, max_value=5.0, value=1.1, step=0.1)
    else:
        league_avg = st.number_input("🌍 Ø Tore pro Spiel in dieser Liga (Liga-Schnitt)", min_value=0.5, max_value=5.0, value=2.6, step=0.1)
        c_as1, c_as2 = st.columns(2)
        with c_as1:
            home_scored = st.number_input("Ø Tore geschossen", min_value=0.0, value=1.5, step=0.1)
            home_conceded = st.number_input("Ø Tore kassiert", min_value=0.0, value=1.0, step=0.1)
        with c_as2:
            away_scored = st.number_input("Ø Tore geschossen (Ausw.)", min_value=0.0, value=1.2, step=0.1)
            away_conceded = st.number_input("Ø Tore kassiert (Ausw.)", min_value=0.0, value=1.4, step=0.1)
        
        avg_team = league_avg / 2.0
        xg_home = (home_scored * away_conceded) / avg_team if avg_team > 0 else 0
        xg_away = (away_scored * home_conceded) / avg_team if avg_team > 0 else 0
        st.success(f"🤖 **Generierte Stärke (Proxy-$xG$):** Heim **{round(xg_home, 2)}** | Auswärts **{round(xg_away, 2)}**")

    probs = calculate_match_probabilities(xg_home, xg_away, rho, zip_factor, 0, 0, 0, False, False)
        
    st.markdown("---")
    st.markdown("### 2. Der xG-Delta-Scanner (Buchmacher vs. Modell)")
    c_odd1, c_oddp, c_odd2 = st.columns(3)
    with c_odd1: b_odd1 = st.number_input("Quote 1 (Heim)", min_value=1.01, value=2.20, step=0.05)
    with c_oddp: b_oddx = st.number_input("Quote X (Draw)", min_value=1.01, value=3.40, step=0.05)
    with c_odd2: b_odd2 = st.number_input("Quote 2 (Auswärts)", min_value=1.01, value=3.20, step=0.05)

    if b_odd1 and b_oddx and b_odd2:
        true_1, true_x, true_2, vig = get_true_probabilities(b_odd1, b_oddx, b_odd2)
        implied_xgh, implied_xga = reverse_engineer_odds(true_1, true_x, true_2, rho, zip_factor)
        delta_h, delta_a = xg_home - implied_xgh, xg_away - implied_xga
        
        st.markdown(f"**📊 Buchmacher-Marge:** {round((vig - 1) * 100, 2)}%")
        c_res1, c_res2 = st.columns(2)
        color_h = "green" if delta_h > 0 else "red"
        color_a = "green" if delta_a > 0 else "red"
        c_res1.markdown(f"**Heim-xG:** Modell {round(xg_home,2)} vs. Buchmacher {round(implied_xgh,2)} <br>👉 Kante: <span style='color:{color_h}; font-weight:bold;'>{delta_h:+.2f} xG</span>", unsafe_allow_html=True)
        c_res2.markdown(f"**Auswärts-xG:** Modell {round(xg_away,2)} vs. Buchmacher {round(implied_xga,2)} <br>👉 Kante: <span style='color:{color_a}; font-weight:bold;'>{delta_a:+.2f} xG</span>", unsafe_allow_html=True)

        ev_1, ev_x, ev_2 = calculate_ev(probs["1"], b_odd1), calculate_ev(probs["X"], b_oddx), calculate_ev(probs["2"], b_odd2)
        eff_kelly, max_allowed_bet = kelly_fraction / parallel_bets, current_bankroll * (max_risk_pct / 100.0)
        
        def process_bet(ev, prob, odd):
            if ev > 0:
                raw_bet = current_bankroll * calculate_kelly(prob, odd, fraction=eff_kelly)
                bet_size = max_allowed_bet if raw_bet > max_allowed_bet else raw_bet
                return round(bet_size, 2) if bet_size >= min_bet else 0.0
            return 0.0

        df_scan = pd.DataFrame({
            "Tipp": ["Heim (1)", "Unentschieden (X)", "Auswärts (2)"],
            "Faire Quote": [format_odds(probs["1"]), format_odds(probs["X"]), format_odds(probs["2"])],
            "Buchmacher": [b_odd1, b_oddx, b_odd2],
            "EV (%)": [round(ev_1 * 100, 2), round(ev_x * 100, 2), round(ev_2 * 100, 2)],
            "Einsatz (€)": [process_bet(ev_1, probs["1"], b_odd1), process_bet(ev_x, probs["X"], b_oddx), process_bet(ev_2, probs["2"], b_odd2)]
        })
        st.dataframe(df_scan, hide_index=True, use_container_width=True)

    with st.expander("➕ Andere Märkte checken & ins Journal eintragen"):
        c_m1, c_m2 = st.columns(2)
        market_options = {"Heim (1)": probs["1"], "Unentschieden (X)": probs["X"], "Auswärts (2)": probs["2"], "Über 2.5": probs["Over25"], "BTTS (Ja)": probs["BTTS"]}
        with c_m1: selected_market = st.selectbox("Markt auswählen", list(market_options.keys()))
        with c_m2: custom_odd = st.number_input("Buchmacher-Quote für diesen Markt", min_value=1.01, value=2.00, step=0.05)
        
        custom_prob = market_options[selected_market]
        custom_ev = calculate_ev(custom_prob, custom_odd)
        raw_k = current_bankroll * calculate_kelly(custom_prob, custom_odd, fraction=(kelly_fraction / parallel_bets))
        max_allowed = current_bankroll * (max_risk_pct / 100.0)
        custom_bet = max_allowed if raw_k > max_allowed else raw_k
        if custom_bet < min_bet: custom_bet = 0
        
        if custom_ev > 0: st.success(f"✅ Value: **+{round(custom_ev * 100, 2)}%** | Einsatz: **{round(custom_bet, 2)} €**")
        else: st.error(f"❌ Kein Value ({round(custom_ev * 100, 2)}%).")

        c_j1, c_j2 = st.columns(2)
        with c_j1: league_name = st.text_input("Liga (z.B. Bundesliga)")
        with c_j2: match_name = st.text_input("Spiel (z.B. Bayern - BVB)")
        if st.button("💾 Wette in SQL-Datenbank speichern"):
            if custom_ev > 0 and custom_bet > 0:
                st.session_state.journal.append({"Liga": league_name, "Spiel": match_name, "Tipp": selected_market, "Quote": custom_odd, "Closing Quote": custom_odd, "Einsatz": round(custom_bet, 2), "EV (%)": round(custom_ev * 100, 2), "Status": "Offen"})
                save_journal(st.session_state.journal)
                st.rerun()

# --- TAB 2: BULK SCANNER ---
with tab_bulk:
    st.header("📂 Bulk-Scanner (Rohdaten-Upload)")
    st.write("Lade hier die CSV-Dateien von FootyStats oder Football-Data.co.uk hoch.")
    
    uploaded_file = st.file_uploader("Lade deine Roh-CSV hoch", type=['csv'])
    
    if uploaded_file is not None:
        try:
            df_raw = pd.read_csv(uploaded_file)
            df_upload, detected_cols = map_raw_columns(df_raw)
            
            st.success(f"✅ Parser hat die Datei gelesen ({len(df_raw)} Spiele).")
            
            if 'Odds_1' not in df_upload.columns or 'Odds_X' not in df_upload.columns or 'Odds_2' not in df_upload.columns:
                st.error("❌ Fehler: Der Parser konnte die Buchmacher-Quoten in der Datei nicht finden (Odds_1, Odds_X, Odds_2 fehlen).")
            elif 'Home_xG' not in df_upload.columns and 'Home_Scored' not in df_upload.columns:
                st.error("❌ Fehler: Weder xG-Daten noch Tor-Schnitte gefunden.")
            else:
                st.write("⚙️ Scanne den Markt nach Ineffizienzen...")
                results = []
                eff_kelly = kelly_fraction / parallel_bets
                max_allowed = current_bankroll * (max_risk_pct / 100.0)

                for index, row in df_upload.iterrows():
                    try:
                        home_team = str(row.get('HomeTeam', f'Heim {index}'))
                        away_team = str(row.get('AwayTeam', f'Auswärts {index}'))
                        o1, ox, o2 = float(row.get('Odds_1', 0)), float(row.get('Odds_X', 0)), float(row.get('Odds_2', 0))
                        
                        if pd.isna(o1) or pd.isna(ox) or pd.isna(o2) or o1 <= 1 or ox <= 1 or o2 <= 1: continue
                        
                        if 'Home_xG' in df_upload.columns and 'Away_xG' in df_upload.columns:
                            xgh, xga = float(row['Home_xG']), float(row['Away_xG'])
                        elif 'Home_Scored' in df_upload.columns and 'Home_Conceded' in df_upload.columns:
                            l_avg = float(row.get('League_Avg', 2.5)) / 2.0
                            hs, hc = float(row['Home_Scored']), float(row['Home_Conceded'])
                            As, ac = float(row['Away_Scored']), float(row['Away_Conceded'])
                            xgh = (hs * ac) / l_avg if l_avg > 0 else 0
                            xga = (As * hc) / l_avg if l_avg > 0 else 0
                        else: continue

                        if pd.isna(xgh) or pd.isna(xga): continue

                        probs = calculate_match_probabilities(xgh, xga, rho, zip_factor)
                        
                        for prob, odd, label in [(probs['1'], o1, '1'), (probs['X'], ox, 'X'), (probs['2'], o2, '2')]:
                            ev = calculate_ev(prob, odd)
                            if ev > 0.02: 
                                raw_bet = current_bankroll * calculate_kelly(prob, odd, fraction=eff_kelly)
                                bet_size = max_allowed if raw_bet > max_allowed else raw_bet
                                if bet_size >= min_bet:
                                    results.append({"Spiel": f"{home_team} - {away_team}", "Tipp": label, "Quote": odd, "EV (%)": round(ev * 100, 2), "Einsatz (€)": round(bet_size, 2)})
                    except: pass 

                if results:
                    st.balloons()
                    df_res = pd.DataFrame(results).sort_values(by="EV (%)", ascending=False)
                    st.write(f"🔥 **Jackpot! Wir haben {len(df_res)} profitable Wetten gefunden:**")
                    st.dataframe(df_res, hide_index=True, use_container_width=True)
                else:
                    st.warning("Keine Wetten mit positivem Value (>2% EV) gefunden.")
        except Exception as e:
            st.error(f"Fehler: {e}")

# --- TAB 3 & 4: JOURNAL & HANDBUCH ---
with tab_journal:
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric("Start-Kapital", f"{start_bankroll:.2f} €")
    kpi2.metric("Akt. Bankroll", f"{current_bankroll:.2f} €", f"{current_bankroll - start_bankroll:.2f} €")
    kpi3.metric("Gebunden", f"{exposure:.2f} €")
    settled_bets = [b for b in st.session_state.journal if b['Status'] in ['Gewonnen', 'Verloren']]
    total_invested = sum(b['Einsatz'] for b in settled_bets)
    if total_invested > 0:
        roi = ((current_bankroll - start_bankroll) / total_invested) * 100
        hitrate = (len([b for b in settled_bets if b['Status'] == 'Gewonnen']) / len(settled_bets)) * 100
        kpi4.metric("ROI", f"{roi:.2f} %", f"Hitrate: {hitrate:.1f}%")
    else: kpi4.metric("ROI", "0.00 %")

    valid_clvs = [((b['Quote'] / b['Closing Quote']) - 1) * 100 for b in st.session_state.journal if pd.notna(b.get('Closing Quote')) and float(b.get('Closing Quote', 0)) > 0]
    avg_clv = sum(valid_clvs) / len(valid_clvs) if valid_clvs else 0.0
    kpi5.metric("Ø CLV", f"{avg_clv:+.2f} %")

    st.markdown("---")
    st.subheader("📋 Historie (Gesichert in Supabase SQL)")
    if len(st.session_state.journal) > 0:
        edited_journal = st.data_editor(
            st.session_state.journal, 
            column_config={"Status": st.column_config.SelectboxColumn("Status", options=["Offen", "Gewonnen", "Verloren"], required=True), "Closing Quote": st.column_config.NumberColumn("Closing Quote", format="%.2f", step=0.01)}, 
            hide_index=True, use_container_width=True
        )
        if edited_journal != st.session_state.journal:
            st.session_state.journal = edited_journal
            save_journal(st.session_state.journal)
            st.rerun()
            
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            csv = pd.DataFrame(st.session_state.journal).to_csv(index=False).encode('utf-8')
            st.download_button("💾 CSV Backup", data=csv, file_name='quant_journal.csv', mime='text/csv')
        with col_btn2:
            if st.button("🗑️ Journal löschen"):
                st.session_state.journal = []
                save_journal([])
                st.rerun()

with tab_manual:
    st.header("📚 Das Syndikat-Playbook")
    with st.expander("✅ System-Status: Enterprise"):
        st.markdown("""
        Deine App läuft jetzt auf einer **Supabase PostgreSQL Datenbank**. Das bedeutet:
        * Keine Speicherlimits mehr.
        * Maximale Sicherheit.
        * Du kannst 10.000 Wetten tracken, ohne dass die App langsamer wird.
        """)
