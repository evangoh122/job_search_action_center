from models import Job
from scoring import final_score, title_on_allowlist


def _job(title: str, company: str) -> Job:
    return Job(
        id="test",
        source="test",
        company_canonical=company,
        dedupe_key=f"{company}|{title}",
        title=title,
        url="https://example.com",
        ats_type="greenhouse",
    )


def test_target_company_scores_higher_than_random():
    assert final_score(_job("Senior Data Scientist", "Databricks")) > final_score(
        _job("Barista", "Random Cafe")
    )


def test_final_score_in_range():
    for title, company in [
        ("Senior Data Scientist", "Databricks"),
        ("Barista", "Random Cafe"),
        ("Machine Learning Engineer", "OpenAI"),
    ]:
        s = final_score(_job(title, company))
        assert 0.0 <= s <= 100.0


def test_within_24h_boost():
    j = _job("Data Scientist", "Databricks")
    assert final_score(j, within_24h=True) >= final_score(j, within_24h=False)


def test_title_on_allowlist():
    assert title_on_allowlist(_job("Machine Learning Engineer", "X")) is True
    assert title_on_allowlist(_job("Barista", "X")) is False
