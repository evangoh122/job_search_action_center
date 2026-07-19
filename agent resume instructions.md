# Agent Resume Instructions

## Purpose

Create a truthful, job-specific, two-page resume from the candidate's master resume. The master resume is an evidence bank containing product management, AI, and data science projects. Select and reorder the strongest evidence for each vacancy; do not merely rephrase every master-resume bullet.

The tailored resume must make the hiring case for the specific job while preserving the facts, scope, metrics, dates, employers, project names, and level of ownership in the master resume.

The agent must reason about relevance, not rely on exact keyword overlap. It should recognize transferable evidence—for example, customer discovery can support product discovery, model monitoring can support responsible AI operations, and executive dashboards can support data-driven decision-making—provided the underlying work genuinely demonstrates the job requirement.

## Required inputs

Before tailoring, obtain:

1. The complete job description, including title, responsibilities, required skills, preferred skills, seniority, industry, and location.
2. The master resume or structured achievement bank.
3. Any applicable length or format constraint.

If the job description or master resume is incomplete, identify the missing information. Never fill a gap with an assumption.

## Non-negotiable rules

- Use only claims supported by the master resume or other candidate-provided evidence.
- Never invent or estimate a metric, team size, budget, date, technology, customer, revenue impact, or level of ownership.
- Do not turn participation into leadership. Preserve distinctions such as led, owned, partnered, contributed, supported, and analyzed.
- Do not claim production deployment when the evidence describes a prototype, proof of concept, academic project, or recommendation.
- Do not claim model improvement without a named baseline and evaluation measure in the evidence.
- Use a job-description keyword only when the candidate's evidence supports it. Keyword stuffing is prohibited.
- Preserve confidentiality. Generalize sensitive names or figures only when the master resume already does so.
- Keep the final resume internally consistent: the summary, skills, bullets, titles, and chronology must not contradict one another.
- Flag weak or missing evidence instead of fabricating a polished claim.
- Keep the completed resume to two pages. Enforce the limit by selecting and editing content, never by reducing font size, narrowing margins, compressing line spacing, or creating dense keyword lists.
- Preserve the approved resume template's font family and font sizes exactly. Font-size reduction is prohibited, even if the draft exceeds two pages.

## Tailoring workflow

### 1. Build the job success profile

Extract the job description into the following groups:

- **Primary outcomes:** what the person is expected to deliver.
- **Core capabilities:** the five to eight skills repeatedly emphasized or essential to the role.
- **Domain context:** industry, customer, business function, regulatory setting, and data environment.
- **Methods and tools:** frameworks, platforms, programming languages, analytics methods, and AI techniques.
- **Leadership signals:** strategy, roadmaps, stakeholder influence, people leadership, execution, or hands-on depth.
- **Screening constraints:** required years, degree, location, work authorization, certifications, or language.

Classify every requirement as `required`, `preferred`, or `contextual`. Do not give a repeated but generic word more weight than a concrete required outcome.

### 2. Classify the role

Choose a primary role family and, when justified, one secondary family:

- **Product management:** prioritize customer problems, product strategy, discovery, prioritization, roadmaps, experimentation, adoption, commercialization, stakeholder alignment, and business outcomes.
- **AI product management:** prioritize product judgment plus model capability, evaluation, responsible AI, human-in-the-loop design, data readiness, technical trade-offs, deployment, and adoption.
- **Data science / applied AI:** prioritize problem formulation, data preparation, methodology, experimentation, model evaluation, deployment or operationalization, monitoring, and measurable business impact.
- **Data / analytics:** prioritize decision support, KPI design, data quality, pipelines, dashboards, governance, analytical insight, and operating efficiency.

For a hybrid role, keep one coherent narrative. Do not make the candidate appear to be three unrelated professionals.

### 3. Match evidence to requirements

Score each master-resume achievement before selecting it:

| Criterion | Score |
| --- | ---: |
| Directly demonstrates a primary job outcome | +4 |
| Supports a required capability | +3 |
| Uses the same truthful domain or method | +2 |
| Contains a clear quantified result | +2 |
| Shows the ownership level required by the role | +2 |
| Supports only a preferred requirement | +1 |
| Shares a tool but not the underlying problem or outcome | +0.5 |
| Requires an unsupported inference | Exclude |

Prefer evidence that matches the job's outcome and context over evidence that merely contains the same software keyword. Select the highest-scoring non-duplicative achievements.

Use three kinds of valid evidence matching:

1. **Direct match:** the achievement demonstrates the same outcome, capability, domain, or method requested by the job.
2. **Transferable match:** the terminology differs, but the achievement demonstrates the same underlying competency or operating problem. State the connection using accurate language; do not pretend the contexts were identical.
3. **Supporting match:** the achievement strengthens the candidacy through leadership, scale, industry knowledge, or technical depth but is not a primary requirement.

Direct matches should dominate the resume. Use transferable matches when they make a clear hiring argument. Include supporting matches only after the primary requirements are well covered.

Reject a point when its relevance depends only on a shared tool, a broad word such as `strategy` or `AI`, or an unsupported interpretation of the candidate's responsibilities.

Recommended final mix for six bullets:

- Three bullets addressing the role's primary outcomes.
- One or two bullets showing relevant execution methods or technical depth.
- One bullet showing leadership, stakeholder influence, scale, or operationalization.

Adjust this mix to the vacancy. A technical data scientist role may need more modeling evidence; a product leadership role may need more strategy, adoption, and cross-functional delivery evidence.

### 4. Resolve ambiguous relevance

When a master-resume point could support several role families, interpret it through the outcome most relevant to the vacancy while preserving the original facts.

For example, the same truthful project may emphasize:

- product discovery, prioritization, and adoption for a product role;
- evaluation design, data readiness, and human oversight for an AI product role;
- feature engineering, validation, and model performance for a data science role;
- KPI design, data pipelines, and decision support for an analytics role.

Change emphasis and ordering, not history. Do not add work that the candidate did not perform. If the intended interpretation cannot be verified from the master resume, add a candidate question rather than using the point.

### 5. Map keywords truthfully

Create a keyword map with these columns:

| Job keyword or phrase | Priority | Supporting master-resume evidence | Use in resume? |
| --- | --- | --- | --- |

Use the employer's exact phrase when it is a truthful synonym for the candidate's evidence. For example, `stakeholder management` may become `cross-functional stakeholder management` if the evidence names the functions involved. Do not replace a specific, accurate term with a fashionable but broader claim.

Place important keywords in evidence-bearing locations:

- Summary: two to four defining capabilities, not a keyword list.
- Skills: only demonstrable capabilities and tools.
- Experience bullets: the most important keywords, tied to actions and results.
- Project title or descriptor: only when it accurately identifies the work.

Avoid repeating the same keyword in every bullet.

### 6. Enforce the two-page limit

Treat two pages as a hard editorial constraint. Before writing, allocate space according to relevance rather than trying to fit the entire master resume. The two-page requirement is a content-selection problem, not a typography problem.

Use this default content budget, adjusting modestly for the candidate's career length:

- Header and summary: 10% of the available space.
- Skills: 10%.
- Most relevant recent experience: 45% to 55%.
- Other relevant experience: 20% to 25%.
- Selected projects, education, and certifications: 10% to 20%.
- Approximately 10 to 14 achievement bullets across the entire resume, normally no more than five under one position.

When the draft exceeds two pages, cut content in this order:

1. Unsupported, generic, or responsibility-only statements.
2. Bullets with weak relevance to the target role.
3. Repeated evidence demonstrating a capability already proven more strongly elsewhere.
4. Old or less relevant project detail.
5. Low-priority tools and skills.
6. Excess context that can be compressed without changing the evidence.

Do not cut the strongest measurable outcomes merely because they are older; retain them when they materially prove a critical requirement. Older unrelated roles may be reduced to employer, title, and dates or grouped under `Additional Experience`.

The agent must produce a concise two-page draft, then perform a second editorial pass that removes repetition, shortens weak phrasing, and checks visual density. It must not change the template's font size, font family, margins, or line spacing to force the draft to fit. Render the exact final artifact, require exactly two PDF pages, generate both page previews, and obtain a visual-QA receipt bound to the final résumé hash. If rendering or visual inspection is unavailable, fail closed; `two-page-targeted` is not approval evidence.

## Bullet construction: keyword + XYZ

Use this canonical structure for the achievement bank:

> **Relevant keyword:** Achieved X, measured by Y, by doing Z.

Where:

- **Relevant keyword** is a high-priority phrase from the job description that is supported by the evidence.
- **X (result)** is the outcome created, improved, reduced, enabled, or delivered.
- **Y (measurement)** is the proof: percentage, money, time, adoption, accuracy, coverage, volume, users, experiments, latency, quality, risk reduction, or a clearly stated qualitative milestone.
- **Z (method)** explains how the outcome was achieved, including the candidate's action, approach, collaboration, and relevant method or tool.

The repository's structured achievement format is:

```json
{
  "keyword": "product strategy",
  "result": "Prioritized the launch roadmap around the highest-value customer problems",
  "metric": "three validated use cases selected from 18 discovery interviews",
  "method": "synthesizing customer research, feasibility constraints, and business-value scoring",
  "tags": ["product management", "discovery", "roadmap", "stakeholder management"]
}
```

The rendered evidence-bank bullet is:

> **Product strategy:** Prioritized the launch roadmap around the highest-value customer problems, measured by three validated use cases selected from 18 discovery interviews, by synthesizing customer research, feasibility constraints, and business-value scoring.

For the final human-readable resume, remove the visible `keyword:` label when it makes the sentence sound mechanical, but retain the keyword naturally near the beginning:

> Shaped product strategy and prioritized the launch roadmap around three validated use cases, synthesizing insights from 18 customer interviews with feasibility constraints and business-value scoring.

### When no numeric metric exists

Do not invent one. Use a verified scope, adoption signal, decision, deliverable, or quality threshold as Y. Examples include:

- approval to proceed from the investment committee;
- adoption by sales and operations teams;
- deployment into the production decision workflow;
- coverage across all critical business units;
- a governed definition accepted as the reporting standard.

If there is no defensible result or measurement of any kind, keep the item out of the primary tailored bullets and add it to the evidence-gap list.

## Role-specific bullet emphasis

### Product management

Strong sequence: customer or business problem -> product decision -> cross-functional action -> adoption, revenue, efficiency, risk, or learning result.

Example:

> **Product discovery:** Validated the priority workflow for an analytics product, measured by four recurring pain points identified across 22 user interviews, by leading interviews, journey mapping, and engineering feasibility reviews.

### AI product management

Strong sequence: user outcome -> AI capability and limitation -> evaluation or guardrail -> launch/adoption result.

Example:

> **AI product development:** Improved analyst review speed, measured by a verified reduction in average handling time, by defining the human-in-the-loop workflow, evaluation criteria, and fallback behavior with data science, design, and compliance partners.

Do not describe an API integration as an AI strategy. Name evaluation, data, safety, workflow, or adoption work when the evidence supports it.

### Data science / applied AI

Strong sequence: business problem -> analytical or modeling method -> evaluation -> operational or business result.

Example:

> **Machine learning:** Improved customer targeting, measured by lift against the documented baseline, by engineering behavioral features and validating the selected model with an out-of-time test set.

Do not use `improved accuracy` without the actual metric, comparison, validation design, and value from the evidence.

### Data and analytics

Strong sequence: decision or process -> trusted data or analysis -> delivery mechanism -> time, quality, adoption, or business result.

Example:

> **Data analytics:** Reduced the monthly reporting cycle, measured by a 40% faster close, by automating SQL and Python pipelines and standardizing KPI definitions with finance owners.

## Section assembly

### Headline and summary

- Align the headline with the target role without changing the candidate's actual job titles.
- Write two to four lines that establish the candidate's relevant professional identity, domain context, strongest supported differentiators, and scale or outcomes.
- Do not use first-person pronouns, aspirations, generic adjectives, or unsupported years of experience.
- Avoid phrases such as `results-driven`, `dynamic professional`, `passionate`, `guru`, and `proven track record` unless the following text immediately proves the claim.

### Skills

- Group skills for quick scanning, such as `Product`, `AI & Data Science`, `Analytics & Engineering`, and `Domain`.
- Include only skills supported by experience or projects.
- Order skills by job relevance, not alphabetically.
- Do not add tools solely because they occur in the job description.

### Experience and projects

- Preserve employer, title, and date facts exactly.
- Reorder bullets within each role by relevance and strength.
- Keep the strongest result in the first one or two bullets.
- Use projects when they provide stronger evidence for the vacancy than less relevant employment bullets.
- Label personal, academic, consulting, prototype, and production projects accurately.
- Avoid using two bullets to describe the same result.
- Use concise bullets, normally 20 to 35 words. A longer bullet is acceptable only when necessary to preserve important evidence.
- Include only the projects that materially strengthen the case for this vacancy. The master resume is a source library, not the final table of contents.
- A highly relevant project may receive two bullets; a supporting project should normally receive one. Omit unrelated projects completely.

## Required output

Produce the following in order:

1. **Fit brief:** primary role family, secondary role family if applicable, and the three most important hiring outcomes.
2. **Keyword map:** required and preferred keywords mapped to evidence; explicitly mark unsupported terms.
3. **Selected evidence:** the chosen achievements and why each one is relevant.
4. **Tailored two-page resume:** summary, skills, and reordered or rewritten experience/project bullets, within the content budget above.
5. **Evidence gaps:** important job requirements that the master resume does not substantiate.
6. **Change log:** material wording changes, omitted projects, and any claim that needs candidate verification.

Do not output a match percentage unless a transparent scoring rubric and denominator are shown. A keyword overlap score is not equivalent to the probability of receiving an interview.

## Final quality check

Before returning the resume, verify every item:

- [ ] Each selected bullet supports a required or high-value job outcome.
- [ ] Each bullet contains a result, defensible measurement, and method.
- [ ] Every important keyword is supported by evidence.
- [ ] No fact, metric, tool, ownership claim, or production status was invented.
- [ ] Product, AI, and data science projects form one role-relevant narrative.
- [ ] The strongest evidence appears first.
- [ ] Repeated bullets and low-value tool-only matches were removed.
- [ ] Direct, transferable, and supporting matches were distinguished correctly.
- [ ] The exact final PDF has passed the fail-closed rendered gate at exactly two pages.
- [ ] The submitted artifact passes the shared PDF-only harness (file exists, `.pdf` suffix, and
      `%PDF-` byte signature); DOCX remains editing-source only and is never packaged or uploaded.
- [ ] The two-page limit was achieved through selection and concise writing, with no reduction to font size or other template spacing.
- [ ] Grammar, tense, punctuation, capitalization, and date formatting are consistent.
- [ ] The resume remains readable to a human and is not written for an ATS alone.
- [ ] Unsupported requirements and verification questions are explicitly listed.
