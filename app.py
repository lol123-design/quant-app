import streamlit as st
import math

# --- FUNKTIONEN ---

def poisson_prob(k, lambd):
    return (lambd**k * math.exp(-lambd)) / math.factorial(k)

# NEU: Dixon-Coles Korrektur-Algorithmus
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
    prob_1 = 0.0
    prob_x = 0.0
    prob_2 = 0.0
    prob_over_25 = 0.0
    prob_btts = 0.0

    for home_goals in range(8):
        for away_goals in range(8):
            # Basis-Poisson
            prob = poisson_prob(home_goals, xg_home) * poisson_prob(away_goals, xg_away)
            
            # Dixon-Coles Korrektur anwenden
            dc_adj = dixon_coles_adjustment(home_goals, away_goals, xg_home, xg_away, rho)
            prob = prob * dc_adj
            
            # Verhindern von negativen Werten (bei extremen Regler-Einstellungen)
            if prob < 0: prob = 0
            
            # Märkte berechnen
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
                
    # Normalisierung (falls durch DC die Summe leicht von 100% abweicht)
    total_prob = prob_1 + prob_x + prob_2
    return prob_1/total_prob, prob_x/total_prob, prob_2/total_prob, prob_over_25, prob_btts

def calculate_ev(prob, odds):
    return (prob * odds) - 1

def calculate_kelly(prob, odds, fraction=0.25):
    kelly_full = (prob * (odds - 1) - (1 - prob)) / (odds - 1)
    if kelly_full < 0:
        return 0
    return kelly_full * fraction


# --- APP UI ---
st.set_page_config(page_title="Quant Betting Engine", page_icon="📈")
st.title("📈 Pro Quant Engine v2.0")
st.markdown("Erweitert um die **Dixon-Coles Unentschieden-Korrektur** für maximale Präzision.")

st.sidebar.header("⚙️ Engine Settings")
# Rho ist standardmäßig negativ (meist -0.15 im Profi-Bereich)
rho = st.sidebar.slider("Dixon-Coles Faktor (Unentschieden-Korrektur)", min_value=-0.30, max_value=0.00, value=-0.15, step=0.01)
st.sidebar.info("Tipp: Belasse den Faktor bei ca. -0.15. Er erhöht realistisch die Chancen auf ein 0:0 oder 1:1.")

st.sidebar.header("🏦 Bankroll Management")
bankroll = st.sidebar.number_input("Aktuelle Bankroll (€)", min_value=1.0, value=10.0, step=0.5)
min_bet = st.sidebar.number_input("Mindesteinsatz (€)", min_value=0.1, value=0.5, step=0.1)

st.header("1. Tordaten ($xG$) eingeben")
col1, col2 = st.columns(2)
with col1:
    xg_home = st.number_input("Erwartete Tore Heim ($xG$)", min_value=0.1, max_value=5.0, value=1.5, step=0.1)
with col2:
    xg_away = st.number_input("Erwartete Tore Auswärts ($xG$)", min_value=0.1, max_value=5.0, value=1.1, step=0.1)

# Berechnung mit neuem rho
p1, px, p2, p_over25, p_btts = calculate_match_probabilities(xg_home, xg_away, rho)

st.subheader("💡 Die fairen Modell-Quoten (Dixon-Coles bereinigt)")
col3, col4, col5 = st.columns(3)
col3.metric("Faire Quote 1", round(1/p1, 2) if p1 > 0 else 0, f"{round(p1*100, 1)}%")
col4.metric("Faire Quote X", round(1/px, 2) if px > 0 else 0, f"{round(px*100, 1)}%")
col5.metric("Faire Quote 2", round(1/p2, 2) if p2 > 0 else 0, f"{round(p2*100, 1)}%")

col6, col7 = st.columns(2)
col6.metric("Über 2.5 Tore", round(1/p_over25, 2) if p_over25 > 0 else 0, f"{round(p_over25*100, 1)}%")
col7.metric("Beide treffen (Ja)", round(1/p_btts, 2) if p_btts > 0 else 0, f"{round(p_btts*100, 1)}%")

st.markdown("---")
st.header("2. Value-Check & Einsatz")
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
