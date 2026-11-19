import unittest
from unittest.mock import patch

from flask import Flask
from openpyxl import load_workbook

from database import (
    _adapt_statement,
    insert_id,
    product_search_pattern,
    product_search_subquery,
)
from controllers.admin.common import DashboardInputError
from controllers.admin.customers import handle_action as handle_customer_action
from controllers.admin.employees import handle_action as handle_employee_action
from controllers.admin.inventory import handle_action
from controllers.admin.statistics_export import _build_excel, _build_pdf
from controllers.admin.analytics import get_period
from controllers.admin import dashboard_bp


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

    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class TransactionFakeConnection:
    def __init__(self, row=None):
        self.statements = []
        self.parameters = []
        self.row = row or {"Status": "COMPLETED", "OrderStatus": "PAID"}

    def execute(self, statement, parameters):
        self.statements.append(str(statement))
        self.parameters.append(parameters)
        return TransactionFakeResult(self.row)


class CatalogFakeResult:
    def __init__(self, rows=None, value=None):
        self.rows = rows or []
        self.value = value

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def scalar_one(self):
        return self.value

    def fetchall(self):
        return self.rows


class CatalogFakeConnection:
    def __init__(self):
        self.statements = []
        self.parameters = []

    def execute(self, statement, parameters=None):
        sql = str(statement)
        self.statements.append(sql)
        self.parameters.append(dict(parameters or {}))
        if "SELECT CategoryID, CategoryName, ParentID" in sql:
            return CatalogFakeResult(
                rows=[
                    {
                        "CategoryID": 10,
                        "CategoryName": "Máy tính để bàn (PC)",
                        "ParentID": None,
                    },
                    {
                        "CategoryID": 11,
                        "CategoryName": "Máy đồng bộ",
                        "ParentID": 10,
                    },
                ]
            )
        if "SELECT COUNT(*)" in sql:
            return CatalogFakeResult(value=30)
        return CatalogFakeResult(rows=[])


class CatalogFakeConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class CatalogFakeEngine:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return CatalogFakeConnectionContext(self.connection)


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
        self.assertIn("UPDATE Orders SET OrderStatus=:deleted_status", connection.statements[1])
        self.assertNotIn("DELETE FROM", connection.statements[1])
        self.assertEqual(
            connection.parameters[1],
            {"id": 17, "deleted_status": "DELETED:PAID"},
        )

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

    def test_inbound_restore_recovers_previous_status(self):
        connection = TransactionFakeConnection({"Status": "DELETED:CANCELLED"})
        with self.app.test_request_context(
            "/dashboard/action/inbound-restore",
            method="POST",
            data={"id": "3"},
        ):
            handle_action(connection, "inbound-restore")

        self.assertEqual(
            connection.parameters[1],
            {"id": 3, "status": "CANCELLED"},
        )

    def test_outbound_restore_recovers_previous_status(self):
        connection = TransactionFakeConnection({"OrderStatus": "DELETED:SHIPPED"})
        with self.app.test_request_context(
            "/dashboard/action/outbound-restore",
            method="POST",
            data={"id": "17"},
        ):
            handle_action(connection, "outbound-restore")

        self.assertEqual(
            connection.parameters[1],
            {"id": 17, "status": "SHIPPED"},
        )

    def test_restore_legacy_deleted_transaction_uses_default_status(self):
        connection = TransactionFakeConnection({"Status": "DELETED"})
        with self.app.test_request_context(
            "/dashboard/action/inbound-restore",
            method="POST",
            data={"id": "4"},
        ):
            handle_action(connection, "inbound-restore")

        self.assertEqual(
            connection.parameters[1],
            {"id": 4, "status": "COMPLETED"},
        )


class AccountRestoreTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "test"

    def test_employee_restore_reactivates_locked_account(self):
        connection = TransactionFakeConnection()
        with self.app.test_request_context(
            "/dashboard/action/employee-restore",
            method="POST",
            data={"id": "12"},
        ):
            handle_employee_action(connection, "employee-restore")

        self.assertIn(
            "UPDATE Users SET IsDeleted=0, DeletedAt=NULL",
            connection.statements[0],
        )
        self.assertEqual(connection.parameters[0], {"id": 12})

    def test_customer_restore_reactivates_hidden_customer(self):
        connection = TransactionFakeConnection()
        with self.app.test_request_context(
            "/dashboard/action/customer-restore",
            method="POST",
            data={"id": "27"},
        ):
            handle_customer_action(connection, "customer-restore")

        self.assertIn(
            "UPDATE Customers SET IsDeleted=0, DeletedAt=NULL",
            connection.statements[0],
        )
        self.assertEqual(connection.parameters[0], {"id": 27})


class StatisticsExportTests(unittest.TestCase):
    def setUp(self):
        self.period = get_period("day", "2024-06-05")
        self.analytics = {
            "period_sales": 125000,
            "period_order_count": 2,
            "sales_chart": {
                "labels": ["00:00", "01:00"],
                "values": [50000, 75000],
            },
            "category_chart": [
                {"label": "Thiết bị", "value": 125000},
            ],
        }

    def test_excel_contains_summary_revenue_and_categories(self):
        output = _build_excel("day", self.period, self.analytics)

        workbook = load_workbook(output, data_only=True)
        self.assertEqual(workbook.sheetnames, ["Tong quan", "Doanh thu", "Danh muc"])
        self.assertEqual(workbook["Tong quan"]["B4"].value, 125000)
        self.assertEqual(workbook["Tong quan"]["B5"].value, 2)
        self.assertEqual(workbook["Doanh thu"]["B3"].value, 75000)
        self.assertEqual(workbook["Danh muc"]["A2"].value, "Thiết bị")

    def test_pdf_builds_valid_document(self):
        output = _build_pdf("day", self.period, self.analytics)

        self.assertTrue(output.getvalue().startswith(b"%PDF-"))

    def test_download_routes_return_files_for_selected_period(self):
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(dashboard_bp)
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_type"] = "staff"
            session["role_id"] = 1

        with patch(
            "controllers.admin.statistics_export._load_statistics",
            return_value=("month", self.period, self.analytics),
        ):
            excel_response = client.get(
                "/dashboard/statistics/excel?period=month&date=2024-06-05"
            )
            pdf_response = client.get(
                "/dashboard/statistics/pdf?period=month&date=2024-06-05"
            )

        self.assertEqual(excel_response.status_code, 200)
        self.assertIn("Thong_ke_month_2024-06-05.xlsx", excel_response.headers["Content-Disposition"])
        self.assertTrue(excel_response.data.startswith(b"PK"))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertIn("Thong_ke_month_2024-06-05.pdf", pdf_response.headers["Content-Disposition"])
        self.assertTrue(pdf_response.data.startswith(b"%PDF-"))


class CatalogFilterTests(unittest.TestCase):
    def test_category_filter_uses_bounded_indexable_product_query(self):
        from controllers.site import index as site_index

        connection = CatalogFakeConnection()
        app = Flask(__name__)
        with app.test_request_context("/?category=pc&page=99"):
            with patch(
                "controllers.site.engine", CatalogFakeEngine(connection)
            ):
                with patch(
                    "controllers.site.render_template",
                    side_effect=lambda template, **context: context,
                ):
                    context = site_index()

        self.assertEqual(context["page"], 2)
        self.assertEqual(context["total_pages"], 2)
        self.assertEqual(context["total_products"], 30)
        count_query = next(
            query for query in connection.statements if "SELECT COUNT(*)" in query
        )
        product_query = next(
            query for query in connection.statements if "ORDER BY p.ProductID" in query
        )
        self.assertIn("p.CategoryID IN (:category_id_0, :category_id_1)", count_query)
        self.assertIn("LIMIT :limit OFFSET :offset", product_query)
        self.assertEqual(
            connection.parameters[-1],
            {
                "category_id_0": 10,
                "category_id_1": 11,
                "limit": 24,
                "offset": 24,
            },
        )
