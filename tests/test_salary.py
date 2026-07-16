from salary import SalaryRange, aggregate_salary, extract_salary, is_below_monthly_sgd_floor


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


def test_rejects_only_ranges_whose_monthly_maximum_is_below_floor():
    assert is_below_monthly_sgd_floor(
        SalaryRange(9000, 11999, "SGD", "MONTH"), 12000
    )
    assert not is_below_monthly_sgd_floor(
        SalaryRange(9000, 12000, "SGD", "MONTH"), 12000
    )


def test_converts_annual_sgd_maximum_to_monthly():
    assert is_below_monthly_sgd_floor(
        SalaryRange(120000, 143999, "SGD", "YEAR"), 12000
    )
    assert not is_below_monthly_sgd_floor(
        SalaryRange(120000, 144000, "SGD", "YEAR"), 12000
    )


def test_keeps_ambiguous_or_open_ended_salary_data():
    assert not is_below_monthly_sgd_floor(
        SalaryRange(9000, None, "SGD", "MONTH"), 12000
    )
    assert not is_below_monthly_sgd_floor(
        SalaryRange(9000, 11000, "", "MONTH"), 12000
    )
    assert not is_below_monthly_sgd_floor(
        SalaryRange(9000, 11000, "SGD", ""), 12000
    )
