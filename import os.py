import streamlit as st

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
try:
    import mariadb
    DB_ATTIVO = True
except:
    DB_ATTIVO = False
    
# --------------------------------------------------
# UTENTI E PERMESSI
# --------------------------------------------------
UTENTI = {
    "admin": {"password": "admin123", "case": ["casa1", "casa2", "casa3"]},
    "user1": {"password": "user123", "case": ["casa1", "casa2"]},
    "user2": {"password": "user123", "case": ["casa1", "casa3"]},
}

if "loggato" not in st.session_state:
    st.session_state.loggato = False

if not st.session_state.loggato:
    st.title("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Accedi"):
        if username in UTENTI and UTENTI[username]["password"] == password:
            st.session_state.loggato = True
            st.session_state.case_permesse = UTENTI[username]["case"]
            st.rerun()
        else:
            st.error("Username o password sbagliati")

    st.stop()
# --------------------------------------------------
# CONNESSIONE AL DATABASE
# --------------------------------------------------
def get_connection():
    if DB_ATTIVO:
        return mariadb.connect(
            host="localhost",
            user="python_user",
            password="password123",
            database="case_dati"
        )
    else:
        return None
# --------------------------------------------------
# FUNZIONE PER CARICARE I DATI
# --------------------------------------------------
def load_data(casa=None, start_time=None, end_time=None):

    conn = get_connection()

    # --------- CASO STREAMLIT CLOUD (usa CSV) ----------
    if conn is None:
        df = pd.read_csv("dati_case.csv")

        df["data"] = pd.to_datetime(df["data"], format="%Y%m%d%H%M")
        df["guasto"] = df["guasto"].fillna("")

        # filtro casa
        if casa and casa != "Tutte":
            df = df[df["casa"] == casa]

        # filtro data inizio
        # ---- filtro data inizio ----
        if start_time is not None:
            start_time = pd.to_datetime(start_time)
            df = df[df["data"] >= start_time]
        
        # ---- filtro data fine ----
        if end_time is not None:
            end_time = pd.to_datetime(end_time) + pd.Timedelta(days=1)
            df = df[df["data"] < end_time]

        return df

    # --------- CASO LOCALE (usa MariaDB) ----------
    cursor = conn.cursor()

    query = "SELECT * FROM dati_casa WHERE 1=1"
    params = []

    if casa and casa != "Tutte":
        query += " AND casa=?"
        params.append(casa)

    if start_time:
        query += " AND data>=?"
        params.append(start_time)

    if end_time:
        query += " AND data<=?"
        params.append(end_time)

    cursor.execute(query, tuple(params))

    cols = [desc[0] for desc in cursor.description]
    dati = cursor.fetchall()

    df = pd.DataFrame(dati, columns=cols)

    cursor.close()
    conn.close()

    df["data"] = pd.to_datetime(df["data"], format="%Y%m%d%H%M")

    return df

# --------------------------------------------------
# STREAMLIT - INTERFACCIA AVANZATA
# --------------------------------------------------
col1, col2 = st.columns([1,4])

with col1:
    st.image("logo.png", width=120)

with col2:
    st.title("Test Dashboard Gestione Abitazioni")

# --- Filtri ---
case_options = ["Tutte"] + st.session_state.case_permesse
casa = st.selectbox("Seleziona casa", case_options)
start_date = st.date_input("Data inizio", value=None)
end_date = st.date_input("Data fine", value=None)

campo = st.selectbox("Mostra solo valori particolari", ["Tutti", "Guasti", "Energia > valore", "Temperatura > valore"])
valore = None
if "valore" in campo:
    valore = st.number_input("Inserisci valore di riferimento", value=0.0)

# --- Carica dati ---

df = load_data(
    casa=casa,
    start_time=start_date,
    end_time=end_date
)
df = df[df["casa"].isin(st.session_state.case_permesse)]
# --- Filtri avanzati ---
if campo == "Guasti":
    df = df[df["guasto"] != ""]
elif campo == "Energia > valore" and valore is not None:
    df = df[df["energia_consumata_giornaliera_appartamento"] > valore]
elif campo == "Temperatura > valore" and valore is not None:
    df = df[df["temperatura_appartamento"] > valore]

# --- Visualizzazione tabella ---
st.subheader("Dati filtrati")
st.dataframe(df)

# --- Grafico temperatura a 5 minuti ---
# crea una copia dei dati validi
df_temp = df[df["temperatura_appartamento"] != -999]

st.subheader("Grafico temperatura (ogni 5 minuti)")
if not df_temp.empty:
    plt.figure(figsize=(12,4))
    sns.lineplot(data=df_temp, x="data", y="temperatura_appartamento", hue="casa")
    plt.xticks(rotation=45)
    plt.tight_layout()
    fig = plt.gcf()
    st.pyplot(fig)

# --- Energia giornaliera ---
if not df.empty:
    df_daily = df.copy()
    df_daily['giorno'] = df_daily['data'].dt.date  # estrai solo il giorno

    # energia totale giornaliera per casa
    energia_giornaliera = df_daily.groupby(['casa', 'giorno'])['energia_consumata_giornaliera_appartamento'].max().reset_index()

    # delta e percentuale giorno su giorno
    energia_giornaliera['delta'] = energia_giornaliera.groupby('casa')['energia_consumata_giornaliera_appartamento'].diff()
    energia_giornaliera['delta_percent'] = energia_giornaliera.groupby('casa')['energia_consumata_giornaliera_appartamento'].pct_change() * 100

    # --- Visualizzazione tabella giornaliera ---
    st.subheader("Energia giornaliera e variazioni")
    st.dataframe(
        energia_giornaliera.style.format({
            'energia_consumata_giornaliera_appartamento': '{:.0f}',
            'delta': '{:.0f}',
            'delta_percent': '{:.1f}%'
        }).background_gradient(subset=['delta_percent'], cmap='RdYlGn_r')
    )

    # --- Grafico a barre giornaliero ---
    st.subheader("Grafico consumi giornalieri per casa")
    fig3, ax3 = plt.subplots(figsize=(12,4))
    sns.barplot(
        data=energia_giornaliera,
        x='giorno',
        y='energia_consumata_giornaliera_appartamento',
        hue='casa',
        ax=ax3
    )
    plt.xticks(rotation=45)
    plt.tight_layout()
    st.pyplot(fig3)
