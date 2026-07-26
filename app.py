import streamlit as st
import math

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
    # Basis-Märkte
    prob_1 = 0.0
    prob_x = 0.0
    prob_2 = 0.0
    prob_over_25 = 0.0
    prob_btts = 0.0
    
    # Asian Handicap Märkte
    prob_ah_h_minus15 = 0.0
    prob_ah_h_plus15 = 0.0
    prob_ah_a_minus15 = 0.0
    prob_ah_a_plus15 = 0.0

    for home_goals in range(8):
        for away_goals in range(8):
            prob = poisson_prob(home_goals, xg_home) * poisson_prob(away_goals, xg_away)
            dc_adj = dixon_coles_adjustment(home_goals, away_goals, xg_home, xg_away, rho)
            prob = prob * dc_adj
            
            if prob < 0: prob = 0
            
            # 1X2 & Tore
            if home_goals > away_goals:
                prob_1 += prob
            elif home_goals == away_goals:
                prob_x += prob
            else:
                prob_2 += prob
                
            if (home_goals + away_goals) > 2.5:
                prob_over_25 += prob
                
            if home_goals > 0 and away_goals > 0:
                prob_btts += prob
                
            # Asian Handicap Logik
            margin = home_goals - away_goals
            
            if margin >= 2:
                prob_ah_h_minus15 += prob
            if margin >= -1:
                prob_ah_h_plus15 += prob
                
            if margin <= -2:
                prob_ah_a_minus15 += prob
            if margin <= 1:
                prob_ah_a_plus15 += prob

    total_prob = prob_1 + prob_x + prob_2
    
    # Rückgabe als Dictionary für saubere Struktur
    return {
        "1": prob_1/total_prob,
        "X": prob_x/total_prob,
        "2": prob_2/total_prob,
        "Over25": prob_over_25,
        "BTTS": prob_btts,
        "AH_H_minus15": prob_ah_h_minus15,
        "AH_H_plus15": prob_ah_h_plus15,
        "AH_A_minus15": prob_ah_a_minus15,
        "AH_A_plus15": prob_ah_a_plus15
    }

def calculate_ev(prob, odds):
    return (prob * odds) - 1

def calculate_kelly(prob, odds, fraction=0.25):
    kelly_full = (prob * (odds - 1) - (1 - prob)) / (odds - 1)
    if kelly_full < 0:
        return 0
    return kelly_full * fraction

def format_odds(prob):
    if prob <= 0: return 0.0
    return round(1 / prob, 2)

# --- APP UI ---
st.set_page_config(page_title="Quant Betting Engine", page_icon="📈", layout="wide")
st.title("📈 Pro Quant Engine v3.0")
st.markdown("Erweitert um die **Asian Handicap Matrix** für tiefe Markt-Analysen.")

st.sidebar.header("⚙️ Engine Settings")
rho = st.sidebar.slider("Dixon-Coles Faktor", min_value=-0.30, max_value=0.00, value=-0.15, step=0.01)

st.sidebar.header("🏦 Bankroll Management")
bankroll = st.sidebar.number_input("Aktuelle Bankroll (€)", min_value=1.0, value=10.0, step=0.5)
min_bet = st.sidebar.number_input("Mindesteinsatz (€)", min_value=0.1, value=0.5, step=0.1)

st.header("1. Tordaten ($xG$) eingeben")
col1, col2 = st.columns(2)
with col1:
    xg_home = st.number_input("Erwartete Tore Heim ($xG$)", min_value=0.1, max_value=5.0, value=1.5, step=0.1)
with col2:
    xg_away = st.number_input("Erwartete Tore Auswärts ($xG$)", min_value=0.1, max_value=5.0, value=1.1, step=0.1)

# Berechnung starten
probs = calculate_match_probabilities(xg_home, xg_away, rho)

st.markdown("---")
st.subheader("💡 Basis-Märkte (1X2 & Tore)")
col3, col4, col5, col6, col7 = st.columns(5)
col3.metric("Heimsieg (1)", format_odds(probs["1"]), f"{round(probs['1']*100, 1)}%")
col4.metric("Unentschieden (X)", format_odds(probs["X"]), f"{round(probs['X']*100, 1)}%")
col5.metric("Auswärts (2)", format_odds(probs["2"]), f"{round(probs['2']*100, 1)}%")
col6.metric("Über 2.5 Tore", format_odds(probs["Over25"]), f"{round(probs['Over25']*100, 1)}%")
col7.metric("BTTS (Ja)", format_odds(probs["BTTS"]), f"{round(probs['BTTS']*100, 1)}%")

st.subheader("⚖️ Asian Handicap Märkte")
col8, col9, col10, col11 = st.columns(4)
col8.metric("Heim -1.5", format_odds(probs["AH_H_minus15"]), f"{round(probs['AH_H_minus15']*100, 1)}%")
col9.metric("Heim +1.5", format_odds(probs["AH_H_plus15"]), f"{round(probs['AH_H_plus15']*100, 1)}%")
col10.metric("Auswärts -1.5", format_odds(probs["AH_A_minus15"]), f"{round(probs['AH_A_minus15']*100, 1)}%")
col11.metric("Auswärts +1.5", format_odds(probs["AH_A_plus15"]), f"{round(probs['AH_A_plus15']*100, 1)}%")

st.markdown("---")
st.header("2. Value-Check & Einsatz")
col12, col13 = st.columns(2)
with col12:
    target_prob_input = st.number_input("Modell-Wahrscheinlichkeit (%) - Trage hier den Prozentwert deines Tipps ein", min_value=1.0, max_value=99.0, value=float(round(probs['1']*100, 1)), step=0.1)
    target_prob = target_prob_input / 100.0
with col13:
    target_odds = st.number_input("Buchmacher-Quote", min_value=1.01, value=2.00, step=0.05)

ev = calculate_ev(target_prob, target_odds)
kelly = calculate_kelly(target_prob, target_odds, fraction=0.25)
bet_size = bankroll * kelly

if bet_size > 0 and bet_size < min_bet:
    bet_size = min_bet

if ev > 0:
    st.success(f"✅ Positiver Erwartungswert (EV): **+{round(ev * 100, 2)}%**")
    st.metric(label="Empfohlener Einsatz (1/4 Kelly)", value=f"{round(bet_size, 2)} €")
else:
    st.error(f"❌ Negativer Erwartungswert (EV): **{round(ev * 100, 2)}%**")
    st.warning("Kein Value. Finger weg von dieser Wette!")
