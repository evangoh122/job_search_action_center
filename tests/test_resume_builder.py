from __future__ import annotations

from apply.resume_builder import build_resume_variant, classify_role, select_resume_keywords
from apply.resume_builder import build_contact_header
from apply.resume_models import ResumeAchievement
from models import Applicant, Job


def _job() -> Job:
    return Job(
        id="job-1",
        source="test",
        company_canonical="Acme Bank",
        dedupe_key="acme|vp-data",
        title="VP Data Analytics and AI Transformation",
        url="https://example.com/job",
        description=(
            "Lead data analytics, generative ai, data governance, python, sql, "
            "and machine learning delivery across wholesale banking."
        ),
    )


def test_select_resume_keywords_from_job_text():
    keywords = select_resume_keywords(_job(), limit=5)
    assert "data analytics" in keywords
    assert "generative ai" in keywords
    assert len(keywords) <= 5


def test_build_contact_header_includes_github_and_resume_links():
    header = build_contact_header(
        Applicant(
            name="Evan Goh",
            email="evan@example.com",
            phone="+65 1234 5678",
            linkedin_url="https://linkedin.com/in/evan",
            github_url="https://github.com/evan",
            resume_url="https://example.com/resume",
        )
    )

    assert "https://github.com/evan" in header
    assert "https://example.com/resume" in header


def test_build_resume_variant_formats_keyword_xyz_bullets():
    achievements = [
        ResumeAchievement(
            keyword="data analytics",
            result="Reduced monthly reporting cycle time",
            metric="40% faster close for leadership dashboards",
            method="automating SQL and Python data pipelines",
            tags=["python", "sql", "data analytics"],
        ),
        ResumeAchievement(
            keyword="data governance",
            result="Improved trusted data adoption",
            metric="single governed KPI layer across finance teams",
            method="standardising metric definitions and ownership controls",
            tags=["data governance"],
        ),
    ]

    variant = build_resume_variant(_job(), achievements)

    assert variant.keywords
    assert variant.bullets[0].startswith("data analytics: ")
    assert "measured by 40% faster close" in variant.bullets[0]
    assert ", by automating SQL and Python data pipelines." in variant.bullets[0]
    assert variant.text.startswith("- data analytics: ")


def test_build_resume_variant_skips_incomplete_xyz_evidence():
    achievements = [
        ResumeAchievement(keyword="python", result="Automated reporting", metric="", method="using Python")
    ]

    variant = build_resume_variant(_job(), achievements)

    assert variant.bullets == []


def test_domain_keyword_beats_shared_tool_overlap():
    job = Job(
        id="job-2",
        source="test",
        company_canonical="Acme Bank",
        dedupe_key="acme|ml",
        title="Machine Learning Customer Analytics Lead",
        url="https://example.com/job",
        description="machine learning customer analytics in Python on Databricks",
    )
    achievements = [
        ResumeAchievement(
            keyword="risk analytics",
            result="Built a risk app",
            metric="30 users",
            method="using Python and Databricks",
            tags=["risk analytics", "databricks", "python"],
        ),
        ResumeAchievement(
            keyword="machine learning",
            result="Improved product targeting",
            metric="4,500 subsidiaries covered",
            method="using K-means and PCA in Python on Databricks",
            tags=["machine learning", "customer analytics", "databricks", "python"],
        ),
    ]

    variant = build_resume_variant(job, achievements, bullet_limit=1)

    assert variant.bullets[0].startswith("machine learning: ")


def test_build_resume_variant_can_exclude_adjacent_role_tags():
    achievements = [
        ResumeAchievement(
            keyword="credit risk analytics",
            result="Built a risk product",
            metric="30 users",
            method="using Python",
            tags=["risk analytics"],
        ),
        ResumeAchievement(
            keyword="front-office analytics",
            result="Built a sales dashboard",
            metric="150 users",
            method="using Power BI",
            tags=["front-office analytics"],
        ),
    ]

    variant = build_resume_variant(
        _job(),
        achievements,
        exclude_tags={"risk analytics", "credit risk analytics"},
    )

    assert len(variant.bullets) == 1
    assert variant.bullets[0].startswith("front-office analytics: ")


def test_resume_variant_includes_required_agent_outputs_and_flags_gaps():
    achievements = [
        ResumeAchievement(
            keyword="machine learning",
            result="Built customer targeting models",
            metric="4,500 subsidiaries covered",
            method="developing K-means and PCA models in Python",
            tags=["machine learning", "python"],
        )
    ]

    variant = build_resume_variant(_job(), achievements)

    assert variant.fit_brief is not None
    assert variant.fit_brief.primary_role_family in {
        "AI product management",
        "product management",
        "data science / applied AI",
        "data / analytics",
    }
    assert variant.keyword_map
    assert variant.selected_evidence[0].score >= 4
    assert any("unsupported" in gap.lower() for gap in variant.evidence_gaps)
    assert variant.change_log
    assert variant.pagination_status.startswith("two-page-targeted")


def test_unrelated_achievement_is_excluded_instead_of_ranked_by_metric_only():
    achievement = ResumeAchievement(
        keyword="education operations",
        result="Built a school timetable",
        metric="seven schools",
        method="using an unrelated scheduling process",
        tags=["education"],
    )

    variant = build_resume_variant(_job(), [achievement])

    assert variant.bullets == []


def test_classify_role_uses_primary_and_optional_secondary_family():
    primary, secondary = classify_role(_job())

    assert primary in {"data science / applied AI", "data / analytics"}
    assert secondary in {"", "AI product management", "data science / applied AI", "data / analytics"}


def test_resume_bullet_preserves_common_technical_acronym_casing():
    job = Job(
        id="job-acronym",
        source="test",
        company_canonical="Acme",
        dedupe_key="acme|ai",
        title="AI Engineering Lead",
        url="https://example.com/ai",
        description="Lead AI and SQL delivery using Python APIs",
    )
    achievement = ResumeAchievement(
        keyword="ai",
        result="Built an analytics service",
        metric="100 users",
        method="using Python, SQL, and APIs",
        tags=["ai", "python", "sql", "api"],
    )

    variant = build_resume_variant(job, [achievement])

    assert variant.bullets[0].startswith("AI: ")


def test_disclosure_constrained_evidence_is_not_selected():
    achievement = ResumeAchievement(
        keyword="machine learning",
        result="Improved a confidential model",
        metric="private metric",
        method="using Python",
        disclosure_constraints="Do not disclose externally",
    )
    variant = build_resume_variant(_job(), [achievement])
    assert variant.bullets == []
    assert variant.selected_evidence == []
