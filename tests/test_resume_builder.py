from __future__ import annotations

from apply.resume_builder import build_resume_variant, classify_role, select_resume_keywords
from apply.resume_builder import build_contact_header
from apply.resume_models import ResumeAchievement
from models import Applicant, Job


def _master(block_text: str, **fields: object) -> ResumeAchievement:
    """Build test evidence copied verbatim from a master resume."""
    return ResumeAchievement(
        block_text=block_text,
        provenance="master resume",
        **fields,
    )


def _job() -> Job:
    """Provide a test helper for job."""
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
    """Verify the select resume keywords from job text scenario."""
    keywords = select_resume_keywords(_job(), limit=5)
    assert "data analytics" in keywords
    assert "generative ai" in keywords
    assert len(keywords) <= 5


def test_build_contact_header_includes_github_and_resume_links():
    """Verify the build contact header includes github and resume links scenario."""
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
    """Verify the build resume variant formats keyword xyz bullets scenario."""
    achievements = [
        _master(
            "Reduced monthly reporting cycle time by automating SQL and Python data pipelines.",
            keyword="data analytics",
            result="Reduced monthly reporting cycle time",
            metric="40% faster close for leadership dashboards",
            method="automating SQL and Python data pipelines",
            tags=["python", "sql", "data analytics"],
        ),
        _master(
            "Improved trusted data adoption through a governed KPI layer across finance teams.",
            keyword="data governance",
            result="Improved trusted data adoption",
            metric="single governed KPI layer across finance teams",
            method="standardising metric definitions and ownership controls",
            tags=["data governance"],
        ),
    ]

    variant = build_resume_variant(_job(), achievements)

    assert variant.keywords
    assert variant.bullets[0] == achievements[0].block_text
    assert variant.text == f"- {achievements[0].block_text}\n- {achievements[1].block_text}"


def test_build_resume_variant_skips_incomplete_xyz_evidence():
    """Verify the build resume variant skips incomplete xyz evidence scenario."""
    achievements = [
        _master(
            "Automated reporting using Python.",
            keyword="python", result="Automated reporting", metric="", method="using Python",
        )
    ]

    variant = build_resume_variant(_job(), achievements)

    assert variant.bullets == []


def test_domain_keyword_beats_shared_tool_overlap():
    """Verify the domain keyword beats shared tool overlap scenario."""
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
        _master(
            "Built a risk app for 30 users using Python and Databricks.",
            keyword="risk analytics",
            result="Built a risk app",
            metric="30 users",
            method="using Python and Databricks",
            tags=["risk analytics", "databricks", "python"],
        ),
        _master(
            "Improved product targeting across 4,500 subsidiaries using K-means and PCA.",
            keyword="machine learning",
            result="Improved product targeting",
            metric="4,500 subsidiaries covered",
            method="using K-means and PCA in Python on Databricks",
            tags=["machine learning", "customer analytics", "databricks", "python"],
        ),
    ]

    variant = build_resume_variant(job, achievements, bullet_limit=1)

    assert variant.bullets[0] == achievements[1].block_text


def test_build_resume_variant_can_exclude_adjacent_role_tags():
    """Verify the build resume variant can exclude adjacent role tags scenario."""
    achievements = [
        _master(
            "Built a risk product for 30 users using Python.",
            keyword="credit risk analytics",
            result="Built a risk product",
            metric="30 users",
            method="using Python",
            tags=["risk analytics"],
        ),
        _master(
            "Built a sales dashboard for 150 users using Power BI.",
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
    assert variant.bullets[0] == achievements[1].block_text


def test_resume_variant_includes_required_agent_outputs_and_flags_gaps():
    """Verify the resume variant includes required agent outputs and flags gaps scenario."""
    achievements = [
        _master(
            "Built customer targeting models covering 4,500 subsidiaries using K-means and PCA.",
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
    """Verify the unrelated achievement is excluded instead of ranked by metric only scenario."""
    achievement = _master(
        "Built a school timetable for seven schools.",
        keyword="education operations",
        result="Built a school timetable",
        metric="seven schools",
        method="using an unrelated scheduling process",
        tags=["education"],
    )

    variant = build_resume_variant(_job(), [achievement])

    assert variant.bullets == []


def test_classify_role_uses_primary_and_optional_secondary_family():
    """Verify the classify role uses primary and optional secondary family scenario."""
    primary, secondary = classify_role(_job())

    assert primary in {"data science / applied AI", "data / analytics"}
    assert secondary in {"", "AI product management", "data science / applied AI", "data / analytics"}


def test_resume_bullet_preserves_common_technical_acronym_casing():
    """Verify the resume bullet preserves common technical acronym casing scenario."""
    job = Job(
        id="job-acronym",
        source="test",
        company_canonical="Acme",
        dedupe_key="acme|ai",
        title="AI Engineering Lead",
        url="https://example.com/ai",
        description="Lead AI and SQL delivery using Python APIs",
    )
    achievement = _master(
        "Built an analytics service for 100 users using Python, SQL, and APIs.",
        keyword="ai",
        result="Built an analytics service",
        metric="100 users",
        method="using Python, SQL, and APIs",
        tags=["ai", "python", "sql", "api"],
    )

    variant = build_resume_variant(job, [achievement])

    assert variant.bullets[0] == achievement.block_text


def test_disclosure_constrained_evidence_is_not_selected():
    """Verify the disclosure constrained evidence is not selected scenario."""
    achievement = _master(
        "Improved a confidential model using Python.",
        keyword="machine learning",
        result="Improved a confidential model",
        metric="private metric",
        method="using Python",
        disclosure_constraints="Do not disclose externally",
    )
    variant = build_resume_variant(_job(), [achievement])
    assert variant.bullets == []
    assert variant.selected_evidence == []


def test_resume_variant_rejects_structured_evidence_without_exact_master_block():
    """XYZ metadata alone must never be rewritten into an application bullet."""
    achievement = ResumeAchievement(
        source="master resume",
        keyword="machine learning",
        result="Improved coverage",
        metric="10 models",
        method="using Python",
    )

    variant = build_resume_variant(_job(), [achievement])

    assert variant.bullets == []
    assert variant.selected_evidence == []


def test_resume_variant_rejects_non_master_and_tampered_blocks():
    """A copied block needs master provenance and an intact content fingerprint."""
    non_master = _master(
        "Improved coverage for 10 models using Python.",
        keyword="machine learning", result="Improved coverage", metric="10 models",
        method="using Python",
    ).model_copy(update={"provenance": "interview notes"})
    tampered = _master(
        "Improved coverage for 10 models using Python.",
        keyword="machine learning", result="Improved coverage", metric="10 models",
        method="using Python",
    ).model_copy(update={"block_text": "Changed application-only wording."})

    variant = build_resume_variant(_job(), [non_master, tampered])

    assert variant.bullets == []


def test_resume_variant_preserves_master_block_whitespace_and_punctuation_exactly():
    """Assembly selects and reorders but does not normalize authoritative block text."""
    block = "Led ML delivery — 10 models; 40% faster.  "
    achievement = _master(
        block,
        keyword="machine learning", result="Led ML delivery", metric="10 models",
        method="using Python",
    )

    variant = build_resume_variant(_job(), [achievement])

    assert variant.bullets == [block]
    assert variant.selected_evidence[0].bullet == block
    assert variant.selected_evidence[0].provenance == "master resume"
    assert len(variant.selected_evidence[0].block_hash) == 64
