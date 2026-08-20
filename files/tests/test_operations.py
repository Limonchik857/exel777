import pandas as pd
from django.test import TestCase

from operations.engine import (
    apply_operation,
    drop_columns,
    filter_rows,
    find_replace,
    normalize_phone,
    remove_duplicates,
    remove_empty_rows,
    sort_rows,
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
