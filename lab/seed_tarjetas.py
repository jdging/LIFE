"""Seed de tarjetas de ejemplo para el laboratorio (lab/reinvencion).

Corre con: python3 seed_tarjetas.py

La tarjeta TC1 ("Visa", BNA) es un dato de EJEMPLO inspirado en el caso real
que contó Juan: está a su nombre (`titular='JD'`), pero la usan los dos en
la práctica, por eso `uso_compartido=True` ("es una tarjeta compartida en
la practica, la usamos juntos") — ver README.
"""

import db

TARJETAS_EJEMPLO = [
    {
        "id": "TC1",
        "nombre": "Visa",
        "tipo": "Crédito",
        "banco": "BNA",
        "titular": "JD",
        "dia_cierre": 10,
        "dia_vencimiento": 20,
        "es_default_dinamico": True,
        "uso_compartido": True,
    },
    {
        "id": "TD1",
        "nombre": "Mastercard Débito",
        "tipo": "Débito",
        "banco": "Galicia",
        "titular": "JD",
    },
    {
        "id": "TC2",
        "nombre": "Mastercard",
        "tipo": "Crédito",
        "banco": "Santander",
        "titular": "Pinki",
        "dia_cierre": 5,
        "dia_vencimiento": 15,
    },
]


def main():
    conn = db.get_connection()
    db.init_db(conn)

    existentes = {t["id"] for t in db.get_tarjetas(conn)}
    for tarjeta in TARJETAS_EJEMPLO:
        if tarjeta["id"] in existentes:
            print(f"Tarjeta {tarjeta['id']} ya existe, se omite.")
            continue
        db.insert_tarjeta(conn, tarjeta)
        print(f"Tarjeta {tarjeta['id']} ({tarjeta['nombre']}) insertada.")

    conn.close()


if __name__ == "__main__":
    main()
