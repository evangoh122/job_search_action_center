from salary import SalaryRange, aggregate_salary, extract_salary


def test_extracts_mcf_salary_shape_and_midpoint():
    salary = extract_salary({
        "salary": {"minimum": 9000, "maximum": 13000, "type": {"id": "MONTH"}},
        "salaryCurrency": "SGD",
    })
    assert salary == SalaryRange(9000, 13000, "SGD", "MONTH")
    assert salary.average == 11000


def test_extracts_schema_org_salary_shape():
    salary = extract_salary({
        "baseSalary": {
            "currency": "SGD",
            "value": {"minValue": 120000, "maxValue": 180000, "unitText": "YEAR"},
        }
    })
    assert (salary.minimum, salary.maximum, salary.average) == (120000, 180000, 150000)
    assert (salary.currency, salary.period) == ("SGD", "YEAR")


def test_aggregate_uses_outer_range_and_recomputes_average():
    result = aggregate_salary(
        SalaryRange(9000, 12000, "SGD", "MONTH"),
        SalaryRange(10000, 14000, "SGD", "MONTH"),
    )
    assert result == SalaryRange(9000, 14000, "SGD", "MONTH")
    assert result.average == 11500


def test_incompatible_period_is_not_mixed():
    monthly = SalaryRange(9000, 12000, "SGD", "MONTH")
    assert aggregate_salary(monthly, SalaryRange(120000, 160000, "SGD", "YEAR")) == monthly
