"""Общие помощники для тестов: пользователи, CSV/XLSX файлы."""

from io import BytesIO

import pandas as pd


def make_csv_bytes(df, encoding="utf-8-sig"):
    buf = BytesIO()
    df.to_csv(buf, index=False, encoding=encoding)
    return buf.getvalue()


def make_xlsx_bytes(df):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Data")
    return buf.getvalue()


def sample_df():
    return pd.DataFrame(
        {
            "Name": ["Ivan", "Petr", "Alex", "Ivan", ""],
            "Email": [
                "ivan@mail.ru",
                "petr@mail.ru",
                "alex@mail.ru",
                "ivan@mail.ru",
                "",
            ],
            "Salary": [100000, 80000, 120000, 100000, None],
            "Phone": ["+7 900 000 00 01", "8 (901) 111-22-33", "79020000003", "+7 900 000 00 01", ""],
        }
    )


def sample_other_df():
    return pd.DataFrame(
        {
            "Name": ["Olga", "Max"],
            "Email": ["olga@mail.ru", "max@mail.ru"],
            "Salary": [90000, 110000],
            "Phone": ["+7 903 000 00 00", "89040000000"],
        }
    )
