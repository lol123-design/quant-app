import streamlit as st
import math
import pandas as pd
import requests

st.set_page_config(page_title="Quant Betting Engine", page_icon="📈", layout="wide")

BIN_ID = st.secrets["BIN_ID"]
API_KEY = st.secrets["API_KEY"]
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{BIN_ID}"

def load_journal():
    headers = {"X-Master-Key": API_KEY}
    try:
        req = requests.get(JSONBIN_URL, headers=headers)
        if req.status_code == 200: return req.json().get("record", {}).get("data", [])
        return []
    except: return []

def save_journal(journal_data):
    headers = {"Content-Type": "application/json", "X-Master-Key": API_KEY}
    try: requests.put(JSONBIN_URL, json={"data": journal_data}, headers=headers)
    except: pass

if 'journal' not in st.session_state:
    loaded_data = load_journal()
    for bet in loaded_data:
        if "Liga" not in bet: bet["Liga"] = "Unbekannt"
        if "Closing Quote" not in bet: bet["Closing Quote"] = bet.get("Quote", 0.0)
    st.session_state.journal = loaded_data

# NEU: Das Zero-Inflated Poisson (ZIP) Modell
def zip_poisson(k, lambd, zip_factor):
    p = (lambd**k * math.exp(-lambd)) / math.factorial(k)
    # Wenn k=0 (kein Tor), greift die Zero-Inflation (künstliche Anhebung)
    if k == 0:
        return zip_factor + (1 - zip_factor) * p
    # Alle anderen Tore werden minimal abgesenkt, damit die Summe 100% bleibt
    else:
        return (1 - zip_factor) * p

def dixon_coles_adjustment(home_goals, away_goals, lambd, mu, rho):
    if home_goals == 0 and away_goals == 0: return 1 - (lambd * mu * rho)
    elif home_goals == 1 and away_goals == 0: return 1 + (mu * rho)
    elif home_goals == 0 and away_goals == 1: return 1 + (lambd * rho)
    elif home_goals == 1 and away_goals == 1: return 1 - rho
    else: return 1.0

def calculate_match_probabilities(xg_home, xg_away, rho, zip_factor, current_minute=0, score_home=0, score_away=0):
    prob_1, prob_x, prob_2, prob_over_25, prob_btts = 0.0, 0.0, 0.0, 0.0, 0.0
    prob_ah_h_minus15, prob_ah_h_plus15, prob_ah_a_minus15, prob_ah_a_plus15 = 0.0, 0.0, 0.0, 0.0
    
    time_factor = max((90 - current_minute) / 90.0, 0.001)
    rem_xg_home, rem_xg_away = xg_home * time_factor, xg_away * time_factor

    for added_home in range(8):
        for added_away in range(8):
            # Verwendung der neuen ZIP-Logik statt purem Poisson
            prob = zip_poisson(added_home, rem_xg_home, zip_factor) * zip_poisson(added_away, rem_xg_away, zip_factor)
            prob *= dixon_coles_adjustment(added_home, added_away, rem_xg_home, rem_xg_away, rho)
            if prob < 0: prob = 0
            
            final_home, final_away = score_home + added_home, score_away + added_away
            
            if final_home > final_away: prob_1 += prob
            elif final_home == final_away: prob_x += prob
            else: prob_2 += prob
                
            if (final_home + final_away) > 2.5: prob_over_25 += prob
            if final_home > 0 and final_away > 0: prob_btts += prob
                
            margin = final_home - final_away
            if margin >= 2: prob_ah_h_minus15 += prob
            if margin >= -1: prob_ah_h_plus15 += prob
            if margin <= -2: prob_ah_a_minus15 += prob
            if margin <= 1: prob_ah_a_plus15 += prob

    total_prob = prob_1 + prob_x + prob_2
    p1, px, p2 = prob_1 / total_prob, prob_x / total_prob, prob_2 / total_prob
    
    return {
        "1": p1, "X": px, "2": p2, "Over25": prob_over_25, "BTTS": prob_btts,
        "AH_H_minus15": prob_ah_h_minus15, "AH_H_plus15": prob_ah_h_plus15,
        "AH_A_minus15": prob_ah_a_minus15, "AH_A_plus15": prob_ah_a_plus15,
        "1X": p1 + px, "X2": p2 + px, "12": p1 + p2,
        "DNB1": p1 / (p1 + p2) if (p1 + p2) > 0 else 0, "DNB2": p2 / (p1 + p2) if (p1 + p2) > 0 else 0
    }

def calculate_ev(prob, odds): return (prob * odds) - 1
def calculate_kelly(prob, odds, fraction=0.25):
    k = (prob * (odds - 1) - (1 - prob)) / (odds - 1)
    return k * fraction if k > 0 else 0
def format_odds(prob): return round(1 / prob, 2) if prob > 0 else 0.0

def get_true_probabilities(odds_1, odds_x, odds_2):
    i1, ix, i2 = 1 / odds_1, 1 / odds_x, 1 / odds_2
    vig = i1 + ix + i2
    return i1 / vig, ix / vig, i2 / vig, vig

def reverse_engineer_odds(true_p1, true_px, true_p2, rho, zip_factor):
    best_diff, best_xg_h, best_xg_a = 999.0, 1.0, 1.0
    for h in range(1, 41):
        for a in range(1, 41):
            xgh, xga = h / 10.0, a / 10.0
            probs = calculate_match_probabilities(xgh, xga, rho, zip_factor, 0, 0, 0)
            diff = abs(probs["1"] - true_p1) + abs(probs["X"] - true_px) + abs(probs["2"] - true_p2)
            if diff < best_diff: best_diff, best_xg_h, best_xg_a = diff, xgh, xga
    return best_xg_h, best_xg_a


# --- APP UI ---
st.title("📈 Pro Quant Engine")

# --- SIDEBAR ---
st.sidebar.header("🏦 Start-Kapital")
start_bankroll = st.sidebar.number_input("Initiale Bankroll (€)", min_value=1.0, value=10.0, step=0.5)
min_bet = st.sidebar.number_input("Mindesteinsatz (€)", min_value=0.1, value=0.5, step=0.1)

st.sidebar.header("🛡️ Risikomanagement")
kelly_fraction = st.sidebar.select_slider(
    "Kelly-Strategie", 
    options=[0.125, 0.25, 0.5, 1.0], 
    value=0.25, 
    format_func=lambda x: f"{int(1/x)}/1 Kelly (Defensiv)" if x == 0.125 else (f"{int(1/x)}/1 Kelly (Standard)" if x == 0.25 else (f"{int(1/x)}/1 Kelly (Aggressiv)" if x == 0.5 else "Full Kelly (Wahnsinn)"))
)
parallel_bets = st.sidebar.number_input("Anzahl paralleler Wetten", min_value=1, max_value=20, value=1, step=1)
max_risk_pct = st.sidebar.slider("Max. Einsatz pro Wette (%)", min_value=1.0, max_value=10.0, value=5.0, step=0.5)

st.sidebar.header("⚙️ Engine Settings")
# NEU: Der ZIP-Regler
zip_factor = st.sidebar.slider("ZIP-Faktor (0:0 Boost)", min_value=0.00, max_value=0.20, value=0.05, step=0.01, help="Künstliche Erhöhung der Wahrscheinlichkeit für 0 Tore. Kompensiert die Schwäche von Poisson bei Unentschieden.")
rho = st.sidebar.slider("Dixon-Coles Faktor", min_value=-0.30, max_value=0.00, value=-0.15, step=0.01)

current_bankroll, exposure = start_bankroll, 0.0
for bet in st.session_state.journal:
    current_bankroll -= bet['Einsatz']
    if bet['Status'] == 'Gewonnen': current_bankroll += bet['Einsatz'] * bet['Quote']
    if bet['Status'] == 'Offen': exposure += bet['Einsatz']

tab_engine, tab_reverse, tab_journal = st.tabs(["⚙️ Engine", "🕵️ Reverse", "📖 Portfolio & CLV"])

# --- TAB 1: ENGINE ---
with tab_engine:
    st.markdown("### 1. Daten-Eingabe (Dein Modell)")
    data_mode = st.radio("Wie möchtest du die Team-Stärke berechnen?", ["Direkte xG-Werte eingeben (Große Ligen)", "AS/DS Rechner: Ø Torschnitt (Kleine Ligen)"], horizontal=True)
    
    st.markdown("---")
    if data_mode == "Direkte xG-Werte eingeben (Große Ligen)":
        c_xg1, c_xg2 = st.columns(2)
        with c_xg1: xg_home = st.number_input("Erwartete Tore Heim ($xG$)", min_value=0.1, max_value=5.0, value=1.5, step=0.1)
        with c_xg2: xg_away = st.number_input("Erwartete Tore Auswärts ($xG$)", min_value=0.1, max_value=5.0, value=1.1, step=0.1)
    else:
        st.info("Trage hier die durchschnittlichen Tore ein. Die App generiert daraus einen unabhängigen Proxy-$xG$-Wert.")
        c_as1, c_as2 = st.columns(2)
        with c_as1:
            st.markdown("**Heimteam (Zuhause)**")
            home_scored = st.number_input("Ø Tore geschossen", min_value=0.0, value=1.8, step=0.1)
            home_conceded = st.number_input("Ø Tore kassiert", min_value=0.0, value=0.9, step=0.1)
        with c_as2:
            st.markdown("**Auswärtsteam (Auswärts)**")
            away_scored = st.number_input("Ø Tore geschossen (Ausw.)", min_value=0.0, value=1.1, step=0.1)
            away_conceded = st.number_input("Ø Tore kassiert (Ausw.)", min_value=0.0, value=1.5, step=0.1)
        
        xg_home, xg_away = (home_scored + away_conceded) / 2.0, (away_scored + home_conceded) / 2.0
        st.success(f"🤖 **Generierte Stärke (Proxy-$xG$):** Heim **{round(xg_home, 2)}** | Auswärts **{round(xg_away, 2)}**")

    st.markdown("---")
    with st.expander("⏱️ Live-Wetten Modus aktivieren (Optional)"):
        col_l1, col_l2, col_l3 = st.columns(3)
        with col_l1: live_min = st.number_input("Minute", min_value=0, max_value=90, value=0, step=1)
        with col_l2: live_sh = st.number_input("Stand Heim", min_value=0, max_value=10, value=0, step=1)
        with col_l3: live_sa = st.number_input("Stand Ausw.", min_value=0, max_value=10, value=0, step=1)
    
    probs = calculate_match_probabilities(xg_home, xg_away, rho, zip_factor, live_min, live_sh, live_sa)
        
    st.subheader("💡 Faire Modell-Quoten (ZIP Aktiviert)")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("1", format_odds(probs["1"]))
    c2.metric("X", format_odds(probs["X"]))
    c3.metric("2", format_odds(probs["2"]))
    c4.metric("Über 2.5", format_odds(probs["Over25"]))
    c5.metric("BTTS (Ja)", format_odds(probs["BTTS"]))
    
    st.markdown("---")
    st.header("2. Value-Check & Journal")
    col_input1, col_input2 = st.columns(2)
    with col_input1: target_prob_input = st.number_input("Modell-Wahrscheinlichkeit (%)", min_value=1.0, max_value=99.0, value=float(round(probs['1']*100, 1)), step=0.1)
    with col_input2: target_odds = st.number_input("Buchmacher-Quote", min_value=1.01, value=2.00, step=0.05)

    ev = calculate_ev(target_prob_input / 100.0, target_odds)
    effective_kelly = kelly_fraction / parallel_bets
    raw_kelly_bet = current_bankroll * calculate_kelly(target_prob_input / 100.0, target_odds, fraction=effective_kelly)
    max_allowed_bet = current_bankroll * (max_risk_pct / 100.0)
    
    is_capped = False
    if raw_kelly_bet > max_allowed_bet:
        bet_size, is_capped = max_allowed_bet, True
    else: bet_size = raw_kelly_bet
        
    if bet_size > 0 and bet_size < min_bet: bet_size = min_bet

    if ev > 0:
        st.success(f"✅ Positiver EV: **+{round(ev * 100, 2)}%** | Empfohlener Einsatz: **{round(bet_size, 2)} €**")
        if parallel_bets > 1: st.info(f"🔄 Einsatz wurde für **{parallel_bets} parallele Wetten** angepasst.")
        if is_capped: st.warning(f"⚠️ Einsatz wurde durch dein Sicherheits-Limit ({max_risk_pct}%) gedeckelt.")

        with st.expander("Wette ins Journal übernehmen"):
            c_j1, c_j2, c_j3 = st.columns(3)
            with c_j1: league_name = st.text_input("Liga (z.B. Schweden)")
            with c_j2: match_name = st.text_input("Spiel (z.B. Team A - Team B)")
            with c_j3: market_name = st.text_input("Tipp (z.B. Heim 1)")
            
            if st.button("Ins Journal eintragen (Cloud Sync)"):
                st.session_state.journal.append({
                    "Liga": league_name if league_name else "Unbekannt",
                    "Spiel": match_name, 
                    "Tipp": market_name, 
                    "Quote": target_odds, 
                    "Closing Quote": target_odds,
                    "Einsatz": round(bet_size, 2), 
                    "EV (%)": round(ev * 100, 2), 
                    "Status": "Offen"
                })
                save_journal(st.session_state.journal)
                st.rerun()
    else: st.error(f"❌ Negativer EV: **{round(ev * 100, 2)}%**. Kein Value.")

# --- TAB 2 bleibt identisch ---
with tab_reverse:
    st.header("🕵️ Buchmacher entschlüsseln")
    st.info("Nutze diesen Tab, um zu sehen, wie der Markt denkt. Vergleiche den Wert dann mit deinen eigenen Berechnungen aus Tab 1.")
    r_col1, r_col2, r_col3 = st.columns(3)
    with r_col1: b_odd1 = st.number_input("Quote 1 (Heim)", min_value=1.01, value=2.50, step=0.05)
    with r_col2: b_oddx = st.number_input("Quote X (Draw)", min_value=1.01, value=3.20, step=0.05)
    with r_col3: b_odd2 = st.number_input("Quote 2 (Auswärts)", min_value=1.01, value=2.80, step=0.05)
    if st.button("🔍 Buchmacher entschlüsseln"):
        true_1, true_x, true_2, vig = get_true_probabilities(b_odd1, b_oddx, b_odd2)
        implied_xgh, implied_xga = reverse_engineer_odds(true_1, true_x, true_2, rho, zip_factor)
        st.info(f"📊 **Buchmacher-Marge (Vig):** {round((vig - 1) * 100, 2)}%")
        c_res1, c_res2 = st.columns(2)
        c_res1.metric("Erwartete Tore HEIM ($xG$)", f"{implied_xgh}")
        c_res2.metric("Erwartete Tore AUSWÄRTS ($xG$)", f"{implied_xga}")

# --- TAB 3: JOURNAL & DASHBOARD (bleibt exakt identisch) ---
with tab_journal:
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric("Start-Kapital", f"{start_bankroll:.2f} €")
    kpi2.metric("Akt. Bankroll", f"{current_bankroll:.2f} €", f"{current_bankroll - start_bankroll:.2f} € Profit")
    kpi3.metric("Gebundenes", f"{exposure:.2f} €")
    
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
    col_chart, col_analytics = st.columns([1.5, 1])
    with col_chart:
        st.subheader("📈 Bankroll Entwicklung")
        if len(settled_bets) > 0:
            history, temp_bankroll = [start_bankroll], start_bankroll
            for bet in settled_bets:
                temp_bankroll -= bet['Einsatz']
                if bet['Status'] == 'Gewonnen': temp_bankroll += bet['Einsatz'] * bet['Quote']
                history.append(temp_bankroll)
            st.line_chart(pd.DataFrame(history, columns=["Bankroll (€)"]), height=250)
    
    with col_analytics:
        st.subheader("🔍 Markt-Analyse")
        if len(settled_bets) > 0:
            df_settled = pd.DataFrame(settled_bets)
            market_stats = []
            for market in df_settled['Tipp'].unique():
                m_bets = df_settled[df_settled['Tipp'] == market]
                count, invested = len(m_bets), m_bets['Einsatz'].sum()
                returned = m_bets.apply(lambda r: r['Einsatz'] * r['Quote'] if r['Status'] == 'Gewonnen' else 0, axis=1).sum()
                profit, m_roi = returned - invested, (returned - invested) / invested * 100 if invested > 0 else 0
                m_clv_list = [((r['Quote'] / r['Closing Quote']) - 1) * 100 for _, r in m_bets.iterrows() if pd.notna(r.get('Closing Quote')) and float(r.get('Closing Quote', 0)) > 0]
                m_avg_clv = sum(m_clv_list) / len(m_clv_list) if m_clv_list else 0.0
                market_stats.append({"Markt": market, "Wetten": count, "Profit (€)": round(profit, 2), "ROI (%)": round(m_roi, 1), "Ø CLV (%)": round(m_avg_clv, 2)})
            st.dataframe(pd.DataFrame(market_stats).sort_values(by="Profit (€)", ascending=False), hide_index=True, use_container_width=True)
            
            st.markdown("---")
            st.subheader("🌍 Ligen-Analyse")
            league_stats = []
            for league in df_settled['Liga'].unique():
                l_bets = df_settled[df_settled['Liga'] == league]
                count, invested = len(l_bets), l_bets['Einsatz'].sum()
                returned = l_bets.apply(lambda r: r['Einsatz'] * r['Quote'] if r['Status'] == 'Gewonnen' else 0, axis=1).sum()
                profit, l_roi = returned - invested, (returned - invested) / invested * 100 if invested > 0 else 0
                l_clv_list = [((r['Quote'] / r['Closing Quote']) - 1) * 100 for _, r in l_bets.iterrows() if pd.notna(r.get('Closing Quote')) and float(r.get('Closing Quote', 0)) > 0]
                l_avg_clv = sum(l_clv_list) / len(l_clv_list) if l_clv_list else 0.0
                league_stats.append({"Liga": league, "Wetten": count, "Profit (€)": round(profit, 2), "ROI (%)": round(l_roi, 1), "Ø CLV (%)": round(l_avg_clv, 2)})
            st.dataframe(pd.DataFrame(league_stats).sort_values(by="Profit (€)", ascending=False), hide_index=True, use_container_width=True)

    st.markdown("---")
    st.subheader("📋 Wett-Historie & CLV-Eingabe")
    if len(st.session_state.journal) > 0:
        edited_journal = st.data_editor(
            st.session_state.journal, 
            column_config={
                "Status": st.column_config.SelectboxColumn("Status", options=["Offen", "Gewonnen", "Verloren"], required=True),
                "Closing Quote": st.column_config.NumberColumn("Closing Quote", format="%.2f", step=0.01)
            }, 
            hide_index=True, 
            use_container_width=True
        )
        if edited_journal != st.session_state.journal:
            st.session_state.journal = edited_journal
            save_journal(st.session_state.journal)
            st.rerun()
            
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            csv = pd.DataFrame(st.session_state.journal).to_csv(index=False).encode('utf-8')
            st.download_button("💾 Als CSV Backup laden", data=csv, file_name='quant_journal.csv', mime='text/csv')
        with col_btn2:
            if st.button("🗑️ Journal löschen"):
                st.session_state.journal = []
                save_journal([])
                st.rerun()
