import os
import re
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# --------------------------------------------------
# CONFIG BASE
# --------------------------------------------------
BASE_DIR = os.path.dirname(__file__)
CSV_PATH = os.path.join(BASE_DIR, "dati_case.csv")
LOGO_PATH = os.path.join(BASE_DIR, "logo.png")
STEP_MINUTI = 5

# FORZA USO SOLO CSV
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
    st.session_state["loggato"] = False

if "case_permesse" not in st.session_state:
    st.session_state["case_permesse"] = []

if "username" not in st.session_state:
    st.session_state["username"] = ""

if "casa_selezionata" not in st.session_state:
    st.session_state["casa_selezionata"] = None

# --------------------------------------------------
# LOGIN
# --------------------------------------------------
if st.session_state["loggato"] is False:
    st.title("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Accedi", key="login_btn"):
        if username in UTENTI and UTENTI[username]["password"] == password:
            st.session_state["loggato"] = True
            st.session_state["username"] = username
            st.session_state["case_permesse"] = UTENTI[username]["case"]
            st.session_state["casa_selezionata"] = None
            st.rerun()
        else:
            st.error("Username o password sbagliati")

    st.stop()

# --------------------------------------------------
# LOAD DATA - SOLO CSV
# --------------------------------------------------
def load_data(casa=None, start_time=None, end_time=None):
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame()

    df = pd.read_csv(CSV_PATH)  
    

    if "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"], format="%Y%m%d%H%M", errors="coerce")

    if "guasto" in df.columns:
        df["guasto"] = df["guasto"].fillna("").astype(str)
    else:
        df["guasto"] = ""

    if casa is not None:
        df = df[df["casa"] == casa]

    if start_time is not None:
        start_time = pd.to_datetime(start_time)
        df = df[df["data"] >= start_time]

    if end_time is not None:
        end_time = pd.to_datetime(end_time) + pd.Timedelta(days=1)
        df = df[df["data"] < end_time]

    return df

# --------------------------------------------------
# PARSING GUASTI
# PRENDE I GUASTI SOLO DALLA COLONNA "guasto"
# --------------------------------------------------
GUASTI_VALIDI = {"luce 1", "luce 2", "luce 3", "temperatura"}

def estrai_guasti_da_testo(valore_guasto):
    if pd.isna(valore_guasto):
        return []

    testo = str(valore_guasto)
    testo = testo.replace("\n", " ").replace("\r", " ").lower().strip()

    if testo == "":
        return []

    parti = re.split(r"[,;|]+", testo)
    guasti = []

    for p in parti:
        p = p.strip()
        if p == "":
            continue

        p = re.sub(r"\s+", " ", p)

        if p.startswith("temp"):
            p = "temperatura"
        elif p.startswith("luce1") or p.startswith("luce 1"):
            p = "luce 1"
        elif p.startswith("luce2") or p.startswith("luce 2"):
            p = "luce 2"
        elif p.startswith("luce3") or p.startswith("luce 3"):
            p = "luce 3"

        if p in GUASTI_VALIDI:
            guasti.append(p)

    return list(dict.fromkeys(guasti))

# --------------------------------------------------
# EVENTI DI GUASTO
# Un evento dura da quando compare a quando scompare.
# fine = timestamp di scomparsa oppure ultimo timestamp + STEP
# --------------------------------------------------
def calcola_eventi_guasto(df):
    colonne_output = ["casa", "guasto", "inizio", "fine", "durata_minuti", "attivo"]

    if df.empty or "data" not in df.columns or "casa" not in df.columns:
        return pd.DataFrame(columns=colonne_output)

    df = df.copy().sort_values(["casa", "data"]).reset_index(drop=True)
    eventi = []

    for casa_corrente, gruppo in df.groupby("casa"):
        gruppo = gruppo.sort_values("data").reset_index(drop=True)
        guasti_aperti = {}

        for _, row in gruppo.iterrows():
            timestamp = row["data"]
            guasti_correnti = set(estrai_guasti_da_testo(row.get("guasto", "")))
            guasti_aperti_set = set(guasti_aperti.keys())

            # chiude i guasti spariti
            da_chiudere = guasti_aperti_set - guasti_correnti
            for guasto in da_chiudere:
                inizio = guasti_aperti[guasto]
                fine = timestamp
                durata_minuti = (fine - inizio).total_seconds() / 60

                eventi.append({
                    "casa": casa_corrente,
                    "guasto": guasto,
                    "inizio": inizio,
                    "fine": fine,
                    "durata_minuti": round(durata_minuti, 1),
                    "attivo": False
                })

                del guasti_aperti[guasto]

            # apre i nuovi guasti
            da_aprire = guasti_correnti - guasti_aperti_set
            for guasto in da_aprire:
                guasti_aperti[guasto] = timestamp

        # chiude quelli ancora attivi a fine dataset
        if not gruppo.empty:
            ultimo_timestamp = gruppo.iloc[-1]["data"]
            for guasto, inizio in guasti_aperti.items():
                fine = ultimo_timestamp + pd.Timedelta(minutes=STEP_MINUTI)
                durata_minuti = (fine - inizio).total_seconds() / 60

                eventi.append({
                    "casa": casa_corrente,
                    "guasto": guasto,
                    "inizio": inizio,
                    "fine": fine,
                    "durata_minuti": round(durata_minuti, 1),
                    "attivo": True
                })

    if not eventi:
        return pd.DataFrame(columns=colonne_output)

    eventi_df = pd.DataFrame(eventi)
    eventi_df = eventi_df.sort_values(["casa", "inizio", "guasto"]).reset_index(drop=True)
    return eventi_df

# --------------------------------------------------
# RIEPILOGO CASE
# --------------------------------------------------
def crea_riepilogo_case(df_all, case_permesse):
    colonne_output = ["Casa", "Stato guasti attuale", "Numero errori"]

    if df_all.empty:
        return pd.DataFrame(columns=colonne_output)

    df_all = df_all.copy()
    df_all = df_all[df_all["casa"].isin(case_permesse)]
    df_all = df_all.sort_values(["casa", "data"])

    eventi_df = calcola_eventi_guasto(df_all)
    righe = []

    for casa_corrente in case_permesse:
        df_casa = df_all[df_all["casa"] == casa_corrente].sort_values("data")

        if df_casa.empty:
            righe.append({
                "Casa": casa_corrente,
                "Stato guasti attuale": "Nessun dato",
                "Numero errori": 0
            })
            continue

        ultima_riga = df_casa.iloc[-1]
        guasti_attuali = estrai_guasti_da_testo(ultima_riga.get("guasto", ""))

        stato = "OK" if len(guasti_attuali) == 0 else "GUASTO"
        numero_errori = 0 if eventi_df.empty else len(eventi_df[eventi_df["casa"] == casa_corrente])

        righe.append({
            "Casa": casa_corrente,
            "Stato guasti attuale": stato,
            "Numero errori": numero_errori
        })

    return pd.DataFrame(righe)

# --------------------------------------------------
# HEADER
# --------------------------------------------------
col1, col2, col3 = st.columns([1, 4, 1])

with col1:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=120)

with col2:
    st.title("Test Dashboard Gestione Abitazioni")
    st.caption(f"Utente: {st.session_state.get('username', '')}")
    st.caption("Sorgente dati attuale: CSV")

with col3:
    if st.button("Logout", key="logout_btn"):
        st.session_state.clear()
        st.rerun()

# --------------------------------------------------
# SCHERMATA INIZIALE CASE
# --------------------------------------------------
if st.session_state["casa_selezionata"] is None:
    st.subheader("Case visibili")

    df_all = load_data()
    if not df_all.empty:
        df_all = df_all[df_all["casa"].isin(st.session_state["case_permesse"])]

    riepilogo_case = crea_riepilogo_case(df_all, st.session_state["case_permesse"])

    if riepilogo_case.empty:
        st.info("Nessun dato disponibile.")
    else:
        st.dataframe(riepilogo_case, use_container_width=True)

        st.markdown("### Apri dashboard")

        for _, row in riepilogo_case.iterrows():
            col_a, col_b, col_c, col_d = st.columns([2, 2, 2, 2])

            with col_a:
                st.write(f"**{row['Casa']}**")

            with col_b:
                if row["Stato guasti attuale"] == "OK":
                    st.success("OK")
                elif row["Stato guasti attuale"] == "GUASTO":
                    st.error("GUASTO")
                else:
                    st.warning("N/D")

            with col_c:
                st.write(int(row["Numero errori"]))

            with col_d:
                if st.button("Apri", key=f"apri_{row['Casa']}"):
                    st.session_state["casa_selezionata"] = row["Casa"]
                    st.rerun()

    st.stop()

# --------------------------------------------------
# DASHBOARD SINGOLA CASA
# --------------------------------------------------
if st.button("⬅ Torna alle case", key="back_btn"):
    st.session_state["casa_selezionata"] = None
    st.rerun()

casa = st.session_state["casa_selezionata"]
st.subheader(f"Dashboard della casa: {casa}")

# --------------------------------------------------
# FILTRI DASHBOARD
# --------------------------------------------------
start_date = st.date_input("Data inizio", value=None, key="start_date")
end_date = st.date_input("Data fine", value=None, key="end_date")

campo = st.selectbox(
    "Mostra solo valori particolari",
    ["Tutti", "Guasti", "Energia > valore", "Temperatura > valore"],
    key="campo_dashboard"
)

valore = None
if campo in ["Energia > valore", "Temperatura > valore"]:
    valore = st.number_input("Inserisci valore di riferimento", value=0.0, key="valore_dashboard")

# --------------------------------------------------
# CARICA DATI BASE DELLA CASA
# --------------------------------------------------
df_base = load_data(
    casa=casa,
    start_time=start_date,
    end_time=end_date
)

if not df_base.empty:
    df_base = df_base[df_base["casa"].isin(st.session_state["case_permesse"])].copy()
    df_base["guasti_rilevati"] = df_base["guasto"].apply(estrai_guasti_da_testo)
    df_base["guasti_rilevati_testo"] = df_base["guasti_rilevati"].apply(
        lambda x: ", ".join(x) if x else ""
    )
else:
    df_base = pd.DataFrame()

# --------------------------------------------------
# FILTRI TABELLA PRINCIPALE
# --------------------------------------------------
df = df_base.copy()

if not df.empty:
    if campo == "Guasti":
        df = df[df["guasti_rilevati"].apply(len) > 0]
    elif campo == "Energia > valore" and valore is not None:
        if "energia_consumata_giornaliera_appartamento" in df.columns:
            df = df[df["energia_consumata_giornaliera_appartamento"] > valore]
    elif campo == "Temperatura > valore" and valore is not None:
        if "temperatura_appartamento" in df.columns:
            df = df[df["temperatura_appartamento"] > valore]

# --------------------------------------------------
# TABELLA DATI
# --------------------------------------------------
st.subheader("Dati filtrati")

if df.empty:
    st.info("Nessun dato disponibile con i filtri selezionati.")
else:
    colonne_visibili = list(df.columns)

    if "guasti_rilevati_testo" in colonne_visibili and "guasto" in colonne_visibili:
        colonne_visibili.remove("guasti_rilevati_testo")
        idx = colonne_visibili.index("guasto") + 1
        colonne_visibili.insert(idx, "guasti_rilevati_testo")

    if "guasti_rilevati" in colonne_visibili:
        colonne_visibili.remove("guasti_rilevati")

    st.dataframe(df[colonne_visibili], use_container_width=True)

# --------------------------------------------------
# GRAFICO TEMPERATURA
# --------------------------------------------------
st.subheader("Grafico temperatura (ogni 5 minuti)")

if not df.empty:
    if "temperatura_appartamento" in df.columns:
        df_temp = df[df["temperatura_appartamento"] != -999]
    else:
        df_temp = pd.DataFrame()

    if not df_temp.empty:
        fig, ax = plt.subplots(figsize=(12, 4))
        sns.lineplot(
            data=df_temp,
            x="data",
            y="temperatura_appartamento",
            hue="casa",
            ax=ax
        )
        plt.xticks(rotation=45)
        plt.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
    else:
        st.info("Nessuna temperatura valida da mostrare.")
else:
    st.info("Nessun dato disponibile per il grafico temperatura.")

# --------------------------------------------------
# ENERGIA GIORNALIERA
# --------------------------------------------------
if not df.empty and "energia_consumata_giornaliera_appartamento" in df.columns:
    df_daily = df.copy()
    df_daily["giorno"] = df_daily["data"].dt.date

    energia_giornaliera = (
        df_daily.groupby(["casa", "giorno"])["energia_consumata_giornaliera_appartamento"]
        .max()
        .reset_index()
    )

    energia_giornaliera["delta"] = (
        energia_giornaliera.groupby("casa")["energia_consumata_giornaliera_appartamento"]
        .diff()
    )

    energia_giornaliera["delta_percent"] = (
        energia_giornaliera.groupby("casa")["energia_consumata_giornaliera_appartamento"]
        .pct_change() * 100
    )

    st.subheader("Energia giornaliera e variazioni")
    st.dataframe(
        energia_giornaliera.style.format({
            "energia_consumata_giornaliera_appartamento": "{:.0f}",
            "delta": "{:.0f}",
            "delta_percent": "{:.1f}%"
        }),
        use_container_width=True
    )

    st.subheader("Grafico consumi giornalieri per casa")
    fig2, ax2 = plt.subplots(figsize=(12, 4))
    sns.barplot(
        data=energia_giornaliera,
        x="giorno",
        y="energia_consumata_giornaliera_appartamento",
        hue="casa",
        ax=ax2
    )
    plt.xticks(rotation=45)
    plt.tight_layout()
    st.pyplot(fig2)
    plt.close(fig2)

# --------------------------------------------------
# DEBUG LEGGERO
# --------------------------------------------------
with st.expander("Debug dati base"):
    if df_base.empty:
        st.write("Nessun dato base.")
    else:
        st.dataframe(
            df_base[["data", "guasto", "guasti_rilevati_testo"]].tail(30),
            use_container_width=True
        )

# --------------------------------------------------
# TABELLA EVENTI DI GUASTO
# --------------------------------------------------
st.subheader("Eventi di guasto rilevati")

eventi_guasto_casa = calcola_eventi_guasto(df_base)

if eventi_guasto_casa.empty:
    st.info("Nessun evento di guasto rilevato nel periodo selezionato.")
else:
    eventi_vis = eventi_guasto_casa.rename(columns={
        "casa": "Casa",
        "guasto": "Chi ha causato il guasto",
        "inizio": "Inizio guasto",
        "fine": "Fine guasto",
        "durata_minuti": "Durata (min)",
        "attivo": "Attivo"
    })

    st.dataframe(eventi_vis, use_container_width=True)
