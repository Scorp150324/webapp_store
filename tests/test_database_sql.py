import unittest
from unittest.mock import patch

from flask import Flask

from database import (
    _adapt_statement,
    insert_id,
    product_search_pattern,
    product_search_subquery,
)
from controllers.admin.common import DashboardInputError
from controllers.admin.inventory import handle_action


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


class TransactionFakeResult:
    rowcount = 1

    def first(self):
        return (1,)


class TransactionFakeConnection:
    def __init__(self):
        self.statements = []
        self.parameters = []

    def execute(self, statement, parameters):
        self.statements.append(str(statement))
        self.parameters.append(parameters)
        return TransactionFakeResult()


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

    def test_mysql_search_uses_prefix_pattern_and_escape(self):
        with patch("database.engine", FakeEngine("mysql")):
            subquery = product_search_subquery()
            pattern = product_search_pattern("Dell_100%")

        self.assertIn("ProductName LIKE :search ESCAPE '='", subquery)
        self.assertIn("Specifications LIKE :search ESCAPE '='", subquery)
        self.assertEqual(subquery.count(" UNION "), 3)
        self.assertEqual(pattern, "Dell=_100=%%")

    def test_postgresql_search_uses_lowercase_prefix_expression(self):
        with patch("database.engine", FakeEngine("postgresql")):
            subquery = product_search_subquery()
            pattern = product_search_pattern("DeLl")

        self.assertIn("lower(ProductName) LIKE :search ESCAPE '='", subquery)
        self.assertEqual(pattern, "dell%")


class InventoryTransactionTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "test"

    def test_outbound_soft_delete_marks_record_without_hard_delete(self):
        connection = TransactionFakeConnection()
        with self.app.test_request_context(
            "/dashboard/action/outbound-delete",
            method="POST",
            data={"id": "17"},
        ):
            handle_action(connection, "outbound-delete")

        self.assertEqual(len(connection.statements), 2)
        self.assertIn("UPDATE Orders SET OrderStatus='DELETED'", connection.statements[1])
        self.assertNotIn("DELETE FROM", connection.statements[1])
        self.assertEqual(connection.parameters[1], {"id": 17})

    def test_inbound_update_rejects_unknown_status(self):
        connection = TransactionFakeConnection()
        with self.app.test_request_context(
            "/dashboard/action/inbound-update",
            method="POST",
            data={"id": "3", "supplier_id": "", "status": "DELETED", "notes": ""},
        ):
            with self.assertRaises(DashboardInputError):
                handle_action(connection, "inbound-update")

        self.assertEqual(connection.statements, [])

    def test_inbound_update_changes_supplier_status_and_notes(self):
        connection = TransactionFakeConnection()
        with self.app.test_request_context(
            "/dashboard/action/inbound-update",
            method="POST",
            data={
                "id": "3",
                "supplier_id": "8",
                "status": "COMPLETED",
                "notes": "Đã đối chiếu",
            },
        ):
            handle_action(connection, "inbound-update")

        self.assertIn("UPDATE Inbound_Notes SET SupplierID", connection.statements[1])
        self.assertEqual(
            connection.parameters[1],
            {
                "supplier_id": 8,
                "status": "COMPLETED",
                "notes": "Đã đối chiếu",
                "id": 3,
            },
        )
