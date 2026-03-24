import os
import random
from datetime import datetime, timedelta
import mariadb

# --------------------------------------------------
# CONFIGURAZIONE
# --------------------------------------------------
OUTPUT_FOLDER = "dataset_case"
CASE = ["casa1", "casa2", "casa3"]
START_DATE = datetime(2026, 3, 23, 0, 0)
END_DATE   = datetime(2026, 3, 29, 23, 55)
STEP = timedelta(minutes=5)

# --------------------------------------------------
# CONNESSIONE DATABASE
# --------------------------------------------------
conn = mariadb.connect(
    host="localhost",
    user="python_user",        # cambia se hai un utente diverso
    password="password123",        # inserisci la tua password se l'hai impostata
    database="case_dati"
)
cursor = conn.cursor()

# --------------------------------------------------
# FUNZIONI DATI
# --------------------------------------------------
def next_temperature(prev_temp, hour):
    if 6 <= hour <= 20:
        delta = random.uniform(-0.4, 1)
    else:
        delta = random.uniform(-1, 0.4)
    new_temp = prev_temp + delta
    new_temp = max(prev_temp - 1, min(prev_temp + 1, new_temp))
    new_temp = max(-10, min(40, new_temp))
    return round(new_temp, 1)

def random_lights():
    return random.randint(0,1), random.randint(0,1), random.randint(0,1)

def random_fault():
    if random.random() < 0.03:
        sensors = ["temperatura", "luce1", "luce2", "luce3"]
        return random.sample(sensors, random.randint(1, 4))
    return []

# --------------------------------------------------
# GENERAZIONE DATI CASA
# --------------------------------------------------
def generate_house_data(house_name):
    house_folder = os.path.join(OUTPUT_FOLDER, house_name)
    os.makedirs(house_folder, exist_ok=True)

    current_time = START_DATE
    temperature = random.uniform(16, 22)
    daily_energy = 0

    while current_time <= END_DATE:

        # reset energia a mezzanotte
        if current_time.hour == 0 and current_time.minute == 0:
            daily_energy = 0

        # temperatura
        temperature = next_temperature(temperature, current_time.hour)

        # luci
        luce1, luce2, luce3 = random_lights()
        # potenza istantanea realistica basata sulle luci
        # consumo base di 20, più 10 per ogni luce accesa, più picco casuale fino a 50
        power = 20 + luce1*10 + luce2*10 + luce3*10 + random.randint(0,50)

        # energia cresce in base alla potenza e al passo temporale
        daily_energy += power * (5/60)
        # guasti
        faults = random_fault()
        temp_value = temperature
        if "temperatura" in faults:
            temp_value = -999
        if "luce1" in faults:
            luce1 = -999
        if "luce2" in faults:
            luce2 = -999
        if "luce3" in faults:
            luce3 = -999
        fault_string = ", ".join(faults)

        # timestamp
        timestamp = current_time.strftime("%Y%m%d%H%M")

        # ----- SALVATAGGIO FILE TXT -----
        content = f'''
"casa": "{house_name}",
"data": "{timestamp}",
"temperatura_appartamento": {temp_value},
"stato_luce1": {luce1},
"stato_luce2": {luce2},
"stato_luce3": {luce3},
"energia_consumata_giornaliera_appartamento": {int(daily_energy)},
"potenza_istantanea_consumata_appartamento": {power},
"guasto": "{fault_string}"
'''
        filename = f"{house_name}_{timestamp}.txt"
        filepath = os.path.join(house_folder, filename)
        with open(filepath, "w") as f:
            f.write(content)

        # ----- INSERIMENTO NEL DATABASE -----
        sql = """
        INSERT INTO dati_casa (
            casa, data, temperatura_appartamento, stato_luce1, stato_luce2, stato_luce3,
            energia_consumata_giornaliera_appartamento, potenza_istantanea_consumata_appartamento, guasto
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(sql, (
            house_name,
            current_time.strftime("%Y-%m-%d %H:%M:%S"),
            temp_value,
            luce1,
            luce2,
            luce3,
            daily_energy,
            power,
            fault_string
        ))
        conn.commit()

        current_time += STEP

# --------------------------------------------------
# MAIN
# --------------------------------------------------
def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    for house in CASE:
        generate_house_data(house)
    print("Dataset generato correttamente.")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()
