from models import Job
from scoring import (
    ats_match,
    company_match,
    final_score,
    target_priority,
    tfidf_similarity,
    title_on_allowlist,
)


def _job(title: str, company: str, description: str = "") -> Job:
    """Provide a test helper for job."""
    return Job(
        id="test",
        source="test",
        company_canonical=company,
        dedupe_key=f"{company}|{title}",
        title=title,
        url="https://example.com",
        ats_type="greenhouse",
        description=description,
    )


def test_target_company_scores_higher_than_random():
    """Verify the target company scores higher than random scenario."""
    assert final_score(_job("Senior Data Scientist", "Databricks")) > final_score(
        _job("Barista", "Random Cafe")
    )


def test_final_score_in_range():
    """Verify the final score in range scenario."""
    for title, company in [
        ("Senior Data Scientist", "Databricks"),
        ("Barista", "Random Cafe"),
        ("Machine Learning Engineer", "OpenAI"),
    ]:
        s = final_score(_job(title, company))
        assert 0.0 <= s <= 100.0


def test_within_24h_boost():
    """Verify the within 24h boost scenario."""
    j = _job("Data Scientist", "Databricks")
    assert final_score(j, within_24h=True) >= final_score(j, within_24h=False)


def test_title_on_allowlist():
    """Verify the title on allowlist scenario."""
    assert title_on_allowlist(_job("Head of Data", "X")) is True
    assert title_on_allowlist(_job("Barista", "X")) is False


def test_tfidf_similarity_rewards_relevant_jd():
    """Verify the tfidf similarity rewards relevant jd scenario."""
    relevant = _job("VP Data Analytics", "DBS",
                    "Lead data analytics and AI transformation using Databricks and PySpark.")
    irrelevant = _job("Barista", "Cafe", "Make coffee and serve pastries to customers.")
    assert tfidf_similarity(relevant) > tfidf_similarity(irrelevant)
    assert tfidf_similarity(irrelevant) == 0.0


def test_ats_match_is_keyword_coverage():
    """Verify the ats match is keyword coverage scenario."""
    rich = _job("Head of Data", "DBS",
                "data analytics, ai transformation, databricks, aml, kyc, vice president")
    assert ats_match(rich) > ats_match(_job("Barista", "Cafe", "coffee"))
    assert 0.0 <= ats_match(rich) <= 1.0


def test_match_uses_responsibilities_and_requirements_not_boilerplate():
    """Verify the match uses responsibilities and requirements not boilerplate scenario."""
    from scoring import _relevant_section
    jd = ("About Us. We are a leading bank committed to diversity. "
          "Responsibilities: lead the data analytics and AI transformation roadmap. "
          "Requirements: experience with Databricks, AML, KYC. "
          "Benefits: medical, dental. Equal opportunity employer. How to apply: click here.")
    section = _relevant_section(jd)
    assert "data analytics" in section and "Databricks" in section  # resp + reqs kept
    assert "leading bank" not in section                            # About Us dropped
    assert "medical" not in section and "click here" not in section  # benefits/apply dropped


def test_boilerplate_does_not_inflate_score():
    """Verify the boilerplate does not inflate score scenario."""
    core = "Responsibilities: lead data analytics and AI transformation. Requirements: Databricks."
    boiler = (" About Us: we are a huge global data analytics AI transformation Databricks "
              "powerhouse. " * 5)
    j_core = _job("VP Data", "DBS", core)
    j_boiler = _job("VP Data", "DBS", core + boiler)
    assert abs(final_score(j_core) - final_score(j_boiler)) < 0.1  # boilerplate ignored


def test_junior_titles_score_lower_than_vp():
    """Verify the junior titles score lower than vp scenario."""
    jd = "Lead data analytics and AI transformation. Requirements: Databricks, AML, KYC."
    vp = final_score(_job("Vice President, Data Analytics", "DBS", jd))
    avp = final_score(_job("Assistant Vice President, Data Analytics", "DBS", jd))
    associate = final_score(_job("Associate, Data Analytics", "DBS", jd))
    assert avp < vp
    assert associate < vp


def test_svp_and_vp_not_penalised():
    """Verify the svp and vp not penalised scenario."""
    from scoring import seniority_factor
    assert seniority_factor(_job("Senior Vice President, Data", "DBS")) == 1.0
    assert seniority_factor(_job("SVP, Analytics", "DBS")) == 1.0
    assert seniority_factor(_job("First VP, Data Science", "DBS")) == 1.0
    assert seniority_factor(_job("Vice President, Data", "DBS")) == 1.0
    assert seniority_factor(_job("Assistant Vice President, Data", "DBS")) == 0.80
    assert seniority_factor(_job("Associate, Data", "DBS")) == 0.80


def test_company_match_handles_name_suffix():
    # token-subset: "CIMB Singapore" / "OCBC Bank" still match targets "CIMB" / "OCBC"
    """Verify the company match handles name suffix scenario."""
    assert company_match(_job("VP Data", "CIMB Singapore")) > 0.3
    assert company_match(_job("VP Data", "OCBC Bank")) > 0.3
    assert company_match(_job("VP Data", "Totally Random Co")) == 0.3


def test_tech_companies_are_targeted():
    """Verify the tech companies are targeted scenario."""
    assert target_priority("ByteDance Singapore") == 1
    assert target_priority("Anthropic") == 1
    assert target_priority("Netflix Singapore") == 1
    assert target_priority("Dell Technologies Singapore") == 1
    assert target_priority("Samsung Electronics") == 1
    assert target_priority("Airwallex Singapore") == 2
    assert target_priority("Cloudflare") == 2


def test_additional_workday_financial_employers_are_targeted():
    """Verify the additional workday financial employers are targeted scenario."""
    assert target_priority("Wells Fargo Singapore") == 1
    assert target_priority("State Street Singapore") == 2
    assert target_priority("Northern Trust Singapore") == 2
