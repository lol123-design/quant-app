import streamlit as st
import math
import pandas as pd

# --- SESSION STATE (Das Gedächtnis der App) ---
if 'journal' not in st.session_state:
    st.session_state.journal = []

# --- FUNKTIONEN ---
def poisson_prob(k, lambd):
    return (lambd**k * math.exp(-lambd)) / math.factorial(k)

def dixon_coles_adjustment(home_goals, away_goals, lambd, mu, rho):
    if home_goals == 0 and away_goals == 0:
        return 1 - (lambd * mu * rho)
    elif home_goals == 1 and away_goals == 0:
        return 1 + (mu * rho)
    elif home_goals == 0 and away_goals == 1:
        return 1 + (lambd * rho)
    elif home_goals == 1 and away_goals == 1:
        return 1 - rho
    else:
        return 1.0

def calculate_match_probabilities(xg_home, xg_away, rho):
    prob_1, prob_x, prob_2 = 0.0, 0.0, 0.0
    prob_over_25, prob_btts = 0.0, 0.0
    prob_ah_h_minus15, prob_ah_h_plus15 = 0.0, 0.0
    prob_ah_a_minus15, prob_ah_a_plus15 = 0.0, 0.0

    for home_goals in range(8):
        for away_goals in range(8):
            prob = poisson_prob(home_goals, xg_home) * poisson_prob(away_goals, xg_away)
            prob *= dixon_coles_adjustment(home_goals, away_goals, xg_home, xg_away, rho)
            if prob < 0: prob = 0
            
            if home_goals > away_goals: prob_1 += prob
            elif home_goals == away_goals: prob_x += prob
            else: prob_2 += prob
                
            if (home_goals + away_goals) > 2.5: prob_over_25 += prob
            if home_goals > 0 and away_goals > 0: prob_btts += prob
                
            margin = home_goals - away_goals
            if margin >= 2: prob_ah_h_minus15 += prob
            if margin >= -1: prob_ah_h_plus15 += prob
            if margin <= -2: prob_ah_a_minus15 += prob
            if margin <= 1: prob_ah_a_plus15 += prob

    total_prob = prob_1 + prob_x + prob_2
    
    return {
        "1": prob_1/total_prob, "X": prob_x/total_prob, "2": prob_2/total_prob,
        "Over25": prob_over_25, "BTTS": prob_btts,
        "AH_H_minus15": prob_ah_h_minus15, "AH_H_plus15": prob_ah_h_plus15,
        "AH_A_minus15": prob_ah_a_minus15, "AH_A_plus15": prob_ah_a_plus15
    }

def calculate_ev(prob, odds):
    return (prob * odds) - 1

def calculate_kelly(prob, odds, fraction=0.25):
    kelly_full = (prob * (odds - 1) - (1 - prob)) / (odds - 1)
    if kelly_full < 0: return 0
    return kelly_full * fraction

def format_odds(prob):
    if prob <= 0: return 0.0
    return round(1 / prob, 2)


# --- APP UI ---
st.set_page_config(page_title="Quant Betting Engine", page_icon="📈", layout="wide")
st.title("📈 Pro Quant Engine v4.0")

# --- SIDEBAR ---
st.sidebar.header("🏦 Start-Kapital")
start_bankroll = st.sidebar.number_input("Initiale Bankroll (€)", min_value=1.0, value=10.0, step=0.5)
min_bet = st.sidebar.number_input("Mindesteinsatz (€)", min_value=0.1, value=0.5, step=0.1)

st.sidebar.header("⚙️ Engine Settings")
rho = st.sidebar.slider("Dixon-Coles Faktor", min_value=-0.30, max_value=0.00, value=-0.15, step=0.01)

# --- BERECHNUNG AKTUELLE BANKROLL ---
# Die Bankroll berechnet sich on-the-fly aus dem Journal
current_bankroll = start_bankroll
exposure = 0.0
for bet in st.session_state.journal:
    current_bankroll -= bet['Einsatz']
    if bet['Status'] == 'Gewonnen':
        current_bankroll += bet['Einsatz'] * bet['Quote']
    if bet['Status'] == 'Offen':
        exposure += bet['Einsatz']

# --- TABS LAYOUT ---
tab_engine, tab_journal = st.tabs(["⚙️ Quant Engine", "📖 Portfolio & Journal"])

with tab_engine:
    st.header("1. Match-Analyse ($xG$)")
    col1, col2 = st.columns(2)
    with col1:
        xg_home = st.number_input("Erwartete Tore Heim ($xG$)", min_value=0.1, max_value=5.0, value=1.5, step=0.1)
    with col2:
        xg_away = st.number_input("Erwartete Tore Auswärts ($xG$)", min_value=0.1, max_value=5.0, value=1.1, step=0.1)

    probs = calculate_match_probabilities(xg_home, xg_away, rho)

    st.markdown("---")
    st.subheader("💡 Faire Modell-Quoten")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("1", format_odds(probs["1"]))
    c2.metric("X", format_odds(probs["X"]))
    c3.metric("2", format_odds(probs["2"]))
    c4.metric("Über 2.5", format_odds(probs["Over25"]))
    c5.metric("BTTS (Ja)", format_odds(probs["BTTS"]))
    
    c6, c7, c8, c9 = st.columns(4)
    c6.metric("Heim -1.5", format_odds(probs["AH_H_minus15"]))
    c7.metric("Heim +1.5", format_odds(probs["AH_H_plus15"]))
    c8.metric("Auswärts -1.5", format_odds(probs["AH_A_minus15"]))
    c9.metric("Auswärts +1.5", format_odds(probs["AH_A_plus15"]))

    st.markdown("---")
    st.header("2. Value-Check & Wette einbuchen")
    col10, col11 = st.columns(2)
    with col10:
        target_prob_input = st.number_input("Modell-Wahrscheinlichkeit (%)", min_value=1.0, max_value=99.0, value=float(round(probs['1']*100, 1)), step=0.1)
        target_prob = target_prob_input / 100.0
    with col11:
        target_odds = st.number_input("Buchmacher-Quote", min_value=1.01, value=2.00, step=0.05)

    ev = calculate_ev(target_prob, target_odds)
    bet_size = current_bankroll * calculate_kelly(target_prob, target_odds, fraction=0.25)
    
    if bet_size > 0 and bet_size < min_bet: bet_size = min_bet

    if ev > 0:
        st.success(f"✅ Positiver EV: **+{round(ev * 100, 2)}%** | Empfohlener Einsatz: **{round(bet_size, 2)} €**")
        
        # Formular zum Eintragen
        with st.expander("Wette ins Journal übernehmen"):
            match_name = st.text_input("Spiel (z.B. Sparta Prag - Brünn)")
            market_name = st.text_input("Tipp (z.B. Heim -1.5)")
            if st.button("Ins Journal eintragen"):
                new_bet = {
                    "Spiel": match_name,
                    "Tipp": market_name,
                    "Quote": target_odds,
                    "Einsatz": round(bet_size, 2),
                    "EV (%)": round(ev * 100, 2),
                    "Status": "Offen"
                }
                st.session_state.journal.append(new_bet)
                st.rerun() # Läd die Seite neu, um die Bankroll sofort zu aktualisieren
    else:
        st.error(f"❌ Negativer EV: **{round(ev * 100, 2)}%**. Kein Value.")

with tab_journal:
    st.header("Dein Quant Portfolio")
    
    # Portfolio KPIs
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Start-Kapital", f"{start_bankroll:.2f} €")
    kpi2.metric("Aktuelle Bankroll", f"{current_bankroll:.2f} €", f"{current_bankroll - start_bankroll:.2f} € Gewinn/Verlust")
    kpi3.metric("Gebundenes Kapital", f"{exposure:.2f} €")
    
    # ROI & Hitrate Berechnung
    settled_bets = [b for b in st.session_state.journal if b['Status'] in ['Gewonnen', 'Verloren']]
    total_invested = sum(b['Einsatz'] for b in settled_bets)
    if total_invested > 0:
        profit = current_bankroll - start_bankroll
        roi = (profit / total_invested) * 100
        won_bets = len([b for b in settled_bets if b['Status'] == 'Gewonnen'])
        hitrate = (won_bets / len(settled_bets)) * 100
        kpi4.metric("ROI", f"{roi:.2f} %", f"Hitrate: {hitrate:.1f}%")
    else:
        kpi4.metric("ROI", "0.00 %")

    st.markdown("### Laufende & Ausgewertete Wetten")
    if len(st.session_state.journal) > 0:
        st.info("💡 Klicke doppelt in die Spalte 'Status', um eine Wette auf 'Gewonnen' oder 'Verloren' zu setzen.")
        
        # Interaktive Tabelle
        edited_journal = st.data_editor(
            st.session_state.journal,
            column_config={
                "Status": st.column_config.SelectboxColumn(
                    "Status",
                    options=["Offen", "Gewonnen", "Verloren"],
                    required=True
                )
            },
            hide_index=True,
            use_container_width=True
        )
        
        # Speichert Änderungen sofort in der Session
        if edited_journal != st.session_state.journal:
            st.session_state.journal = edited_journal
            st.rerun()
            
        if st.button("Journal komplett löschen"):
            st.session_state.journal = []
            st.rerun()
    else:
        st.write("Dein Journal ist noch leer. Berechne eine Wette in der Engine und füge sie hinzu!")
