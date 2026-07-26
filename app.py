import streamlit as st
import math

# --- FUNKTIONEN ---

# 1. Poisson-Formel
def poisson_prob(k, lambd):
    return (lambd**k * math.exp(-lambd)) / math.factorial(k)

# 2. Expected Goals (xG) Engine
def calculate_match_probabilities(xg_home, xg_away):
    prob_1 = 0.0
    prob_x = 0.0
    prob_2 = 0.0
    prob_over_25 = 0.0
    prob_btts = 0.0

    # Wir berechnen alle Ergebnisse von 0:0 bis 7:7
    for home_goals in range(8):
        for away_goals in range(8):
            prob = poisson_prob(home_goals, xg_home) * poisson_prob(away_goals, xg_away)
            
            # 1X2 Markt
            if home_goals > away_goals:
                prob_1 += prob
            elif home_goals == away_goals:
                prob_x += prob
            else:
                prob_2 += prob
                
            # Über 2.5 Tore
            if (home_goals + away_goals) > 2.5:
                prob_over_25 += prob
                
            # Beide treffen (BTTS)
            if home_goals > 0 and away_goals > 0:
                prob_btts += prob
                
    return prob_1, prob_x, prob_2, prob_over_25, prob_btts

# 3. Kelly & EV
def calculate_ev(prob, odds):
    return (prob * odds) - 1

def calculate_kelly(prob, odds, fraction=0.25):
    kelly_full = (prob * (odds - 1) - (1 - prob)) / (odds - 1)
    if kelly_full < 0:
        return 0
    return kelly_full * fraction

def calculate_true_prob(odds_1, odds_x, odds_2):
    impl_1 = 1 / odds_1
    impl_x = 1 / odds_x
    impl_2 = 1 / odds_2
    vig = impl_1 + impl_x + impl_2
    return impl_1 / vig, vig


# --- APP UI ---
st.title("📈 Pro Quant Betting Engine")
st.markdown("Basierend auf Poisson-Verteilung und Expected Goals ($xG$).")

st.sidebar.header("🏦 Bankroll Management")
bankroll = st.sidebar.number_input("Aktuelle Bankroll (€)", min_value=1.0, value=10.0, step=0.5)
min_bet = st.sidebar.number_input("Mindesteinsatz (€)", min_value=0.1, value=0.5, step=0.1)

st.header("1. Tordaten & Engine ($xG$)")
col1, col2 = st.columns(2)
with col1:
    xg_home = st.number_input("Erwartete Tore Heim ($xG$)", min_value=0.1, max_value=5.0, value=1.5, step=0.1)
with col2:
    xg_away = st.number_input("Erwartete Tore Auswärts ($xG$)", min_value=0.1, max_value=5.0, value=1.1, step=0.1)

# Berechnungen Engine
p1, px, p2, p_over25, p_btts = calculate_match_probabilities(xg_home, xg_away)

st.subheader("💡 Die fairen Modell-Quoten")
st.markdown("Die App hat diese Wahrscheinlichkeiten & Quoten basierend auf den $xG$-Werten errechnet. Suche beim Buchmacher nach Quoten, die **höher** sind als diese hier:")

col3, col4, col5 = st.columns(3)
col3.metric("Faire Quote 1", round(1/p1, 2) if p1 > 0 else 0, f"{round(p1*100, 1)}%")
col4.metric("Faire Quote X", round(1/px, 2) if px > 0 else 0, f"{round(px*100, 1)}%")
col5.metric("Faire Quote 2", round(1/p2, 2) if p2 > 0 else 0, f"{round(p2*100, 1)}%")

col6, col7 = st.columns(2)
col6.metric("Über 2.5 Tore", round(1/p_over25, 2) if p_over25 > 0 else 0, f"{round(p_over25*100, 1)}%")
col7.metric("Beide treffen (Ja)", round(1/p_btts, 2) if p_btts > 0 else 0, f"{round(p_btts*100, 1)}%")

st.markdown("---")

st.header("2. Value-Check & Einsatz")
st.markdown("Trage hier die echte Buchmacher-Quote und deine Modell-Wahrscheinlichkeit von oben ein, um den Einsatz zu berechnen.")

col8, col9 = st.columns(2)
with col8:
    target_prob_input = st.number_input("Modell-Wahrscheinlichkeit (%)", min_value=1.0, max_value=99.0, value=float(round(p1*100, 1)), step=0.1)
    target_prob = target_prob_input / 100.0
with col9:
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
