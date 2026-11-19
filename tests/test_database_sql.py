import unittest
from unittest.mock import patch

from database import _adapt_statement, insert_id


class FakeDialect:
    def __init__(self, name):
        self.name = name


class FakeEngine:
    def __init__(self, dialect_name):
        self.dialect = FakeDialect(dialect_name)


class FakeResult:
    lastrowid = 42

    def scalar_one(self):
        return 42


class FakeConnection:
    def __init__(self):
        self.statements = []

    def execute(self, statement, parameters):
        self.statements.append(str(statement))
        return FakeResult()


class DatabaseSqlAdaptationTests(unittest.TestCase):
    def test_mysql_adapts_search_and_intervals(self):
        statement = (
            "SELECT * FROM Products WHERE ProductName ILIKE :search "
            "AND ExpiresAt < CURRENT_TIMESTAMP - INTERVAL '1 day' "
            "AND CreatedAt >= CURRENT_TIMESTAMP - INTERVAL '1 hour' "
            "AND ExpiresAt > CURRENT_TIMESTAMP + INTERVAL '10 minutes'"
        )

        adapted = _adapt_statement(statement, "mysql")

        self.assertIn("ProductName LIKE :search", adapted)
        self.assertIn("DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 1 DAY)", adapted)
        self.assertIn("DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 1 HOUR)", adapted)
        self.assertIn("DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 10 MINUTE)", adapted)

    def test_postgresql_keeps_returning_dialect_unchanged(self):
        statement = 'SELECT ProductID FROM Products WHERE ProductName ILIKE :search'

        self.assertIn(
            'SELECT "ProductID" FROM "Products" WHERE "ProductName" ILIKE :search',
            _adapt_statement(statement, "postgresql"),
        )

    def test_insert_id_uses_one_insert_for_each_dialect(self):
        for dialect, expected_sql in (
            ("mysql", "INSERT INTO Products VALUES (:name)"),
            ("postgresql", 'INSERT INTO "Products" VALUES (:name) RETURNING "ProductID"'),
        ):
            with self.subTest(dialect=dialect):
                connection = FakeConnection()
                with patch("database.engine", FakeEngine(dialect)):
                    result = insert_id(
                        connection,
                        "INSERT INTO Products VALUES (:name)",
                        {"name": "sample"},
                        "ProductID",
                    )

                self.assertEqual(result, 42)
                self.assertEqual(connection.statements, [expected_sql])
