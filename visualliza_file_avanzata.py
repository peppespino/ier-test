import os
import random
import pandas as pd
from datetime import datetime, timedelta
import mariadb

# --------------------------------------------------
# CONFIGURAZIONE
# --------------------------------------------------
OUTPUT_FOLDER = "dataset_case"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

CASE = ["casa1", "casa2", "casa3"]
START_DATE = datetime(2026,3,23,0,0)
END_DATE = datetime(2026,3,29,23,55)
STEP = timedelta(minutes=5)

# --------------------------------------------------
# FUNZIONI DATI
# --------------------------------------------------
def next_temperature(prev_temp, hour):
    if 6 <= hour <= 20:
        delta = random.uniform(-0.4,1)
    else:
        delta = random.uniform(-1,0.4)
    new_temp = prev_temp + delta
    new_temp = max(prev_temp - 1, min(prev_temp + 1, new_temp))
    return round(max(-10, min(40, new_temp)),1)

def random_lights():
    return random.randint(0,1), random.randint(0,1), random.randint(0,1)

def random_fault():
    if random.random() < 0.03:
        sensors = ["temperatura","luce1","luce2","luce3"]
        return random.sample(sensors, random.randint(1,4))
    return []

# --------------------------------------------------
# DATABASE MariaDB
# --------------------------------------------------
def insert_into_db(record):
    try:
        conn = mariadb.connect(
            host="localhost",
            user="python_user",
            password="password123",
            database="case_dati"
        )
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO dati_casa 
            (casa,data,temperatura_appartamento,stato_luce1,stato_luce2,stato_luce3,
             energia_consumata_giornaliera_appartamento,potenza_istantanea_consumata_appartamento,guasto)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            record["casa"],
            record["data"],
            record["temperatura_appartamento"],
            record["stato_luce1"],
            record["stato_luce2"],
            record["stato_luce3"],
            record["energia_consumata_giornaliera_appartamento"],
            record["potenza_istantanea_consumata_appartamento"],
            record["guasto"]
        ))
        conn.commit()
    except mariadb.Error as e:
        print(f"Errore DB: {e}")
    finally:
        cur.close()
        conn.close()

# --------------------------------------------------
# GENERAZIONE DATI
# --------------------------------------------------
all_data = []

for house_name in CASE:
    house_folder = os.path.join(OUTPUT_FOLDER, house_name)
    os.makedirs(house_folder, exist_ok=True)
    
    current_time = START_DATE
    temperature = random.uniform(16,22)
    daily_energy = 0

    while current_time <= END_DATE:
        if current_time.hour==0 and current_time.minute==0:
            daily_energy = 0

        temperature = next_temperature(temperature,current_time.hour)
        luce1, luce2, luce3 = random_lights()
        power = random.randint(20,250)
        daily_energy += power*(5/60)
        faults = random_fault()

        temp_value = temperature if "temperatura" not in faults else -999
        luce1 = luce1 if "luce1" not in faults else -999
        luce2 = luce2 if "luce2" not in faults else -999
        luce3 = luce3 if "luce3" not in faults else -999
        fault_string = ", ".join(faults)

        record = {
            "casa": house_name,
            "data": current_time.strftime("%Y%m%d%H%M"),
            "temperatura_appartamento": temp_value,
            "stato_luce1": luce1,
            "stato_luce2": luce2,
            "stato_luce3": luce3,
            "energia_consumata_giornaliera_appartamento": int(daily_energy),
            "potenza_istantanea_consumata_appartamento": power,
            "guasto": fault_string
        }

        # salva .txt
        filename = f"{house_name}_{record['data']}.txt"
        with open(os.path.join(house_folder, filename),"w") as f:
            f.write(str(record))

        # inserisci in MariaDB
        insert_into_db(record)

        # aggiungi per CSV
        all_data.append(record)

        current_time += STEP

# salva CSV
df = pd.DataFrame(all_data)
df.to_csv(os.path.join(OUTPUT_FOLDER,"dati_case.csv"), index=False)
print("Dati generati: .txt, DB e CSV pronti.")
