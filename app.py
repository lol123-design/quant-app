import streamlit as st

def calculate_true_prob(odds_1, odds_x, odds_2):
    # Implizite Wahrscheinlichkeiten
    impl_1 = 1 / odds_1
    impl_x = 1 / odds_x
    impl_2 = 1 / odds_2
    
    # Buchmacherspanne (Vig)
    vig = impl_1 + impl_x + impl_2
    
    # Reale Wahrscheinlichkeiten
    true_1 = impl_1 / vig
    return true_1, vig

def calculate_ev(prob, odds):
    return (prob * odds) - 1

def calculate_kelly(prob, odds, fraction=0.25):
    # Voll-Kelly
    kelly_full = (prob * (odds - 1) - (1 - prob)) / (odds - 1)
    if kelly_full < 0:
        return 0
    # Fractional Kelly (z.B. 1/4)
    return kelly_full * fraction

# --- APP UI ---
st.title("📈 Quant Betting & Risk Manager")
st.markdown("Dein persönlicher Assistent für De-Vigging, Erwartungswert ($EV$) und Kelly-Einsätze.")

st.sidebar.header("🏦 Bankroll Management")
bankroll = st.sidebar.number_input("Aktuelle Bankroll (€)", min_value=1.0, value=10.0, step=0.5)
min_bet = st.sidebar.number_input("Mindesteinsatz Buchmacher (€)", min_value=0.1, value=0.5, step=0.1)

st.header("1. Quoten & De-Vigging")
col1, col2, col3 = st.columns(3)
with col1:
    odds_1 = st.number_input("Quote Heim (1)", min_value=1.01, value=2.00, step=0.05)
with col2:
    odds_x = st.number_input("Quote Unentschieden (X)", min_value=1.01, value=3.40, step=0.05)
with col3:
    odds_2 = st.number_input("Quote Auswärts (2)", min_value=1.01, value=3.50, step=0.05)

true_prob, vig = calculate_true_prob(odds_1, odds_x, odds_2)

st.info(f"📊 **Buchmacherspanne (Vig):** {round((vig - 1) * 100, 2)}% | **Reale Markt-Chance (Heim):** {round(true_prob * 100, 2)}%")

st.header("2. Modell-Kalkulation")
calc_prob_input = st.slider("Eigene berechnete Wahrscheinlichkeit (%)", min_value=1, max_value=99, value=int(true_prob*100))
calc_prob = calc_prob_input / 100.0

st.header("3. Value & Einsatzberechnung")
target_odds = st.number_input("Zu spielende Quote (z.B. Heim, Handicap, Tore)", min_value=1.01, value=odds_1, step=0.05)

ev = calculate_ev(calc_prob, target_odds)
kelly = calculate_kelly(calc_prob, target_odds, fraction=0.25)
bet_size = bankroll * kelly

# Anpassung an Mindesteinsatz
if bet_size > 0 and bet_size < min_bet:
    bet_size = min_bet

if ev > 0:
    st.success(f"✅ Positiver Erwartungswert (EV): **+{round(ev * 100, 2)}%**")
    st.metric(label="Empfohlener Einsatz (1/4 Kelly)", value=f"{round(bet_size, 2)} €")
else:
    st.error(f"❌ Negativer Erwartungswert (EV): **{round(ev * 100, 2)}%**")
    st.warning("Kein Value. Finger weg von dieser Wette!")
