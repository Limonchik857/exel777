import pandas as pd
from django.test import TestCase

from operations.engine import (
    append_tables,
    apply_operation,
    convert_type,
    drop_columns,
    extract,
    filter_rows,
    find_replace,
    normalize_dates,
    normalize_phone,
    normalize_text,
    remove_duplicates,
    remove_empty_rows,
    sort_rows,
    split_table,
)
from operations.validators import OperationError

from .helpers import sample_df


class OperationEngineTests(TestCase):
    def setUp(self):
        self.df = sample_df()

    def test_remove_duplicates_all_columns(self):
        result, meta = remove_duplicates(self.df)
        self.assertEqual(len(result), 4)
        self.assertEqual(meta["removed"], 1)

    def test_remove_duplicates_subset(self):
        result, meta = remove_duplicates(self.df, {"columns": ["Email"]})
        self.assertEqual(len(result), 4)
        self.assertEqual(meta["removed"], 1)

    def test_remove_duplicates_missing_column(self):
        with self.assertRaises(OperationError):
            remove_duplicates(self.df, {"columns": ["Nope"]})

    def test_drop_columns(self):
        result, meta = drop_columns(self.df, {"columns": ["Salary", "Phone"]})
        self.assertNotIn("Salary", result.columns)
        self.assertNotIn("Phone", result.columns)
        self.assertIn("Name", result.columns)
        self.assertEqual(meta["remaining"], 2)

    def test_drop_all_columns_raises(self):
        with self.assertRaises(OperationError):
            drop_columns(self.df, {"columns": list(self.df.columns)})

    def test_filter_numeric_gt(self):
        result, meta = filter_rows(
            self.df, {"column": "Salary", "operator": "gt", "value": "90000"}
        )
        self.assertEqual(len(result), 3)
        self.assertEqual(meta["removed"], 2)

    def test_filter_text_contains(self):
        result, _ = filter_rows(
            self.df, {"column": "Name", "operator": "contains", "value": "Iv"}
        )
        self.assertEqual(len(result), 2)

    def test_filter_text_not_contains(self):
        result, _ = filter_rows(
            self.df, {"column": "Name", "operator": "not_contains", "value": "Iv"}
        )
        self.assertEqual(len(result), 3)

    def test_filter_eq_text(self):
        result, _ = filter_rows(
            self.df, {"column": "Name", "operator": "eq", "value": "Ivan"}
        )
        self.assertEqual(len(result), 2)

    def test_filter_missing_operator(self):
        with self.assertRaises(OperationError):
            filter_rows(self.df, {"column": "Name", "value": "x"})

    def test_sort_numeric_asc(self):
        result, _ = sort_rows(self.df, {"column": "Salary", "ascending": True})
        import math

        salaries = [s for s in result["Salary"].tolist() if not math.isnan(s)]
        self.assertEqual(salaries, [80000, 100000, 100000, 120000])

    def test_sort_text_desc(self):
        result, _ = sort_rows(self.df, {"column": "Name", "ascending": False})
        self.assertEqual(result.iloc[0]["Name"], "Petr")

    def test_find_replace_all(self):
        result, meta = find_replace(
            self.df, {"find": "mail.ru", "replace": "company.com", "all_columns": True}
        )
        self.assertIn("ivan@company.com", result["Email"].tolist())
        self.assertGreater(meta["replacements"], 0)

    def test_find_replace_column(self):
        result, meta = find_replace(
            self.df,
            {"find": "+7 900", "replace": "+7900", "all_columns": False, "column": "Phone"},
        )
        self.assertIn("+7900 000 00 01", result["Phone"].tolist())
        self.assertEqual(meta["replacements"], 2)

    def test_remove_empty_rows(self):
        result, meta = remove_empty_rows(self.df)
        self.assertEqual(len(result), 4)
        self.assertEqual(meta["removed"], 1)

    def test_normalize_phone(self):
        result, _ = normalize_phone(self.df, {"column": "Phone"})
        phones = result["Phone"].tolist()
        self.assertIn("+79000000001", phones)
        self.assertIn("+79011112233", phones)
        self.assertIn("+79020000003", phones)

    def test_apply_operation_dispatch(self):
        result, meta = apply_operation(self.df, "remove_empty_rows", {})
        self.assertLess(len(result), len(self.df))

    def test_apply_operation_unknown(self):
        with self.assertRaises(OperationError):
            apply_operation(self.df, "time_travel", {})

    def test_whitespace_rows_removed(self):
        df = pd.DataFrame({"A": ["x", "  ", None], "B": ["y", "\t", None]})
        result, meta = remove_empty_rows(df)
        self.assertEqual(len(result), 1)
        self.assertEqual(meta["removed"], 2)


class NewOperationTests(TestCase):
    def setUp(self):
        self.df = sample_df()

    def test_normalize_text_trim_lower(self):
        df = pd.DataFrame({"Name": ["  Ivan ", "PETR"]})
        result, meta = normalize_text(df, {"column": "Name", "modes": ["trim", "lower"]})
        self.assertEqual(result["Name"].tolist(), ["ivan", "petr"])

    def test_normalize_text_title(self):
        df = pd.DataFrame({"Name": ["ivan petrov"]})
        result, _ = normalize_text(df, {"column": "Name", "modes": ["title"]})
        self.assertEqual(result.iloc[0]["Name"], "Ivan Petrov")

    def test_normalize_text_collapse_spaces(self):
        df = pd.DataFrame({"Name": ["  Ivan    Petrov  "]})
        result, _ = normalize_text(
            df, {"column": "Name", "modes": ["trim", "collapse_spaces"]}
        )
        self.assertEqual(result.iloc[0]["Name"], "Ivan Petrov")

    def test_normalize_text_requires_modes(self):
        with self.assertRaises(OperationError):
            normalize_text(self.df, {"column": "Name", "modes": []})

    def test_normalize_dates(self):
        df = pd.DataFrame({"Date": ["01.02.2024", "2024-03-05"]})
        result, meta = normalize_dates(df, {"column": "Date", "format": "DD.MM.YYYY"})
        self.assertEqual(result["Date"].tolist(), ["01.02.2024", "05.03.2024"])
        self.assertEqual(meta["converted"], 2)

    def test_normalize_dates_iso(self):
        df = pd.DataFrame({"Date": ["01.02.2024"]})
        result, _ = normalize_dates(df, {"column": "Date", "format": "YYYY-MM-DD"})
        self.assertEqual(result.iloc[0]["Date"], "2024-02-01")

    def test_normalize_dates_bad_format(self):
        with self.assertRaises(OperationError):
            normalize_dates(self.df, {"column": "Date", "format": "XX"})

    def test_convert_type_number(self):
        df = pd.DataFrame({"N": ["12", "3.5", "x"]})
        result, _ = convert_type(df, {"column": "N", "target": "number"})
        values = result["N"].tolist()
        self.assertEqual(values[:2], [12.0, 3.5])
        import math

        self.assertTrue(math.isnan(values[2]))

    def test_convert_type_text(self):
        df = pd.DataFrame({"N": [12, 3.5]})
        result, _ = convert_type(df, {"column": "N", "target": "text"})
        self.assertEqual(result["N"].tolist(), ["12", "3.5"])

    def test_convert_type_bad_target(self):
        with self.assertRaises(OperationError):
            convert_type(self.df, {"column": "Name", "target": "bubble"})

    def test_extract_email(self):
        df = pd.DataFrame({"Text": ["call ivan@mail.ru now", "no email here"]})
        result, _ = extract(df, {"column": "Text", "mode": "email"})
        self.assertEqual(result["Text"].tolist(), ["ivan@mail.ru", ""])

    def test_extract_phone(self):
        df = pd.DataFrame({"Text": ["+7 900 000 00 01 x", "abc"]})
        result, _ = extract(df, {"column": "Text", "mode": "phone"})
        self.assertEqual(result.iloc[0]["Text"], "79000000001")

    def test_extract_url(self):
        df = pd.DataFrame({"Text": ["see https://example.com/x now"]})
        result, _ = extract(df, {"column": "Text", "mode": "url"})
        self.assertEqual(result.iloc[0]["Text"], "https://example.com/x")

    def test_extract_before_separator(self):
        df = pd.DataFrame({"Text": ["user@mail.ru"]})
        result, _ = extract(df, {"column": "Text", "mode": "before", "separator": "@"})
        self.assertEqual(result.iloc[0]["Text"], "user")

    def test_extract_after_separator(self):
        df = pd.DataFrame({"Text": ["user@mail.ru"]})
        result, _ = extract(df, {"column": "Text", "mode": "after", "separator": "@"})
        self.assertEqual(result.iloc[0]["Text"], "mail.ru")

    def test_extract_bad_mode(self):
        with self.assertRaises(OperationError):
            extract(self.df, {"column": "Name", "mode": "magic"})

    def test_split_table(self):
        df = pd.DataFrame({"Region": ["Moscow", "SPB", "Moscow", "Kazan"]})
        parts, meta = split_table(df, {"column": "Region"})
        self.assertEqual(set(parts.keys()), {"Moscow", "SPB", "Kazan"})
        self.assertEqual(len(parts["Moscow"]), 2)
        self.assertEqual(meta["total"], 4)

    def test_split_missing_column(self):
        with self.assertRaises(OperationError):
            split_table(self.df, {"column": "Region"})

    def test_append_tables(self):
        df1 = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
        df2 = pd.DataFrame({"A": [3], "B": ["z"]})
        merged, meta = append_tables(df1, df2)
        self.assertEqual(len(merged), 3)
        self.assertEqual(meta["added"], 1)
        self.assertEqual(meta["total"], 3)

    def test_append_tables_extra_columns_rejected(self):
        df1 = pd.DataFrame({"A": [1], "B": ["x"]})
        df2 = pd.DataFrame({"A": [2], "C": ["z"]})
        with self.assertRaises(OperationError):
            append_tables(df1, df2)
