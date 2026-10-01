from modules.telchi.investigation.validation.hr_payroll_accounting_traceability.hr_payroll_accounting_traceability_v1 import (
    account_class,
    monthly_headcount,
    norm,
)


def test_hr_account_classes_keep_expense_and_liability_separate():
    assert account_class("6110101", "Sueldos y salarios", 5)[0] == "SALARY_EXPENSE"
    assert account_class("2120101", "Sueldos por pagar", 2)[0] == "SALARIES_PAYABLE"
    assert account_class("2120201", "Aportes sociales por pagar", 2)[0] == "CONTRIBUTIONS_PAYABLE"


def test_hr_categories_are_specific():
    assert account_class("6110102", "Aguinaldo", 5)[0] == "BONUS_EXPENSE"
    assert account_class("6110103", "Vacaciones", 5)[0] == "VACATION_EXPENSE"
    assert account_class("6011510", "Comisiones vendedores", 5)[0] == "SALES_COMMISSION"
    assert account_class("999", "Ventas", 4)[0] == ""


def test_employee_state_rule_does_not_use_activity_as_termination():
    employees = [
        {"EMPID": 1, "ACTIVE": "Y", "STATUS": "E", "STARTDATE": "2025-01-01", "TERMDATE": None, "CLASSIFICATION": "ACTIVE"},
        {"EMPID": 2, "ACTIVE": "N", "STATUS": "E", "STARTDATE": "2024-01-01", "TERMDATE": None, "CLASSIFICATION": "INACTIVE"},
        {"EMPID": 3, "ACTIVE": "N", "STATUS": "T", "STARTDATE": "2023-01-01", "TERMDATE": "2025-05-10", "CLASSIFICATION": "TERMINATED"},
    ]
    series = monthly_headcount(employees, __import__("datetime").date(2025, 6, 1))
    assert series[-1]["HEADCOUNT"] == 1


def test_normalization_supports_spanish_accents():
    assert norm("Aportes sociales / vacaciones") == "APORTES SOCIALES / VACACIONES"
