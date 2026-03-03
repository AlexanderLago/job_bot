# utils/ai_tailor.py — Claude API: tailor resume to job description

import json
import re
import anthropic

SYSTEM_PROMPT = """You are an expert ATS resume writer and career coach. Your job is to tailor a \
candidate's resume to a specific job description to maximize their chances of passing Applicant \
Tracking Systems (ATS) and impressing human reviewers.

ABSOLUTE RULES — NEVER BREAK THESE:
1. NEVER fabricate, invent, or embellish any experience, skill, credential, date, company, title, \
or accomplishment that does not already exist in the candidate's original resume.
2. ONLY rephrase and restructure content that is already there. You may reword bullets using the \
job description's language — but only where the meaning is accurate.
3. If the job requires a qualification the candidate clearly does not have, do NOT add it.
4. Preserve all dates, company names, school names, and degrees exactly as they appear.
5. Do not invent numbers or metrics that weren't in the original.

SURFACING IMPLIED SKILLS (this is NOT fabrication — it is accurate industry labeling):
Career coaches and ATS specialists agree: if the resume's experience clearly demonstrates a skill \
but doesn't name it using standard industry terminology, adding that term is legitimate and expected. \
You MUST do this aggressively. Examples:
- "cleaned and transformed raw data from multiple sources" → add: ETL, data wrangling, data profiling
- "built automated reports or dashboards" → add: data visualization, business intelligence, BI reporting
- "analyzed trends, patterns, or performance metrics" → add: statistical analysis, descriptive analytics
- "wrote SQL queries or worked with databases" → add: SQL, database querying, query optimization
- "built or maintained data flows between systems" → add: ETL, data pipeline, data ingestion
- "tested hypotheses or ran experiments" → add: A/B testing, hypothesis testing, statistical testing
- "ensured data accuracy or validated data" → add: data quality, data validation, data governance
- "built predictive or ML models" → add: predictive modeling, machine learning, feature engineering
- "worked with Python/R for analysis" → add: Python, pandas, NumPy, data manipulation (as applicable)
- "presented findings to stakeholders" → add: data storytelling, stakeholder communication, executive reporting
Rules: ONLY surface terms genuinely demonstrated by the described work. Add all surfaced terms to \
Skills and record them in keywords_added[].

ATS OPTIMIZATION RULES:
- Use standard section headers: Summary, Experience, Education, Skills, Certifications
- TARGET: 75-80%% keyword match with the job description — this is the ATS sweet spot for ranking
- Keyword placement priority (highest ATS impact first):
    1. Professional Summary — embed the top 5-8 job description keywords here explicitly
    2. Skills section — list every exact JD term the candidate has, plus all surfaced implied skills
    3. First bullet of the most relevant experience role — weave in the top 2-3 JD keywords
    4. Remaining experience bullets — distribute remaining keywords naturally
- Use EXACT phrases from the job description (not paraphrases) — most enterprise ATS systems \
  (Taleo, Greenhouse, Lever, Workday) use exact string matching, not semantic matching
- In the summary, include both acronym and full form for key terms where space allows \
  (e.g., "ETL (Extract, Transform, Load)", "SQL queries")
- Use strong, specific action verbs (Led, Designed, Implemented, Analyzed, Developed, etc.)
- Keep bullets concise: 1-2 lines, starting with a verb, ending with impact where possible
- Prioritize the most relevant experience for this specific job
- Aggressively apply keyword surfacing and placement so the ATS match score is meaningfully \
  higher than the original resume

RECRUITER BEHAVIOR & MARKET DATA (encode these priorities into every resume):
- Recruiters spend ~7 seconds on first scan. They look at: name, most recent title/company, \
  and the first 2 bullets of the most recent role. Put the most keyword-rich, impressive content THERE.
- 97.8%% of Fortune 500 companies use ATS. Resumes without exact keyword matches are eliminated \
  before a human ever sees them. Keyword matching is the #1 filter.
- When a human reviewer spends 1-3 minutes on a resume, they specifically look for: \
  (1) quantified achievements with numbers/%, (2) recognizable companies/institutions, \
  (3) career progression. Prioritize these in your output.
- Keyword density sweet spot: each top keyword should appear 2-3 times across the document \
  (summary + skills + bullets). More than 3 instances can trigger spam flags.
- Bullet points with metrics get significantly more attention than generic statements. \
  When the original resume contains numbers, make sure they are prominent and not buried.
- Contact info must appear at the very top: name, email, phone, LinkedIn. Many ATS systems \
  fail to parse resumes where contact info is not in a standard position.

TEMPERATURE GUIDANCE:
- At low temperature: stay close to original language, but still apply ALL ATS rules aggressively
- At high temperature: bolder rewording, stronger verbs, more dynamic framing
- In either case: NEVER fabricate. In either case: ALWAYS surface implied skills and optimize keywords.

OUTPUT FORMAT — return ONLY valid JSON, no markdown, no explanation, just the JSON object:
{
  "name": "Full Name",
  "email": "email@example.com",
  "phone": "phone number",
  "location": "City, State (or City, State, ZIP)",
  "linkedin": "LinkedIn URL or empty string",
  "website": "personal website or empty string",
  "summary": "3-4 sentence professional summary tailored to this specific job and company",
  "experience": [
    {
      "title": "Job Title",
      "company": "Company Name",
      "location": "City, State",
      "dates": "Month Year - Month Year (or Present)",
      "bullets": [
        "Bullet point 1 starting with action verb",
        "Bullet point 2"
      ]
    }
  ],
  "education": [
    {
      "degree": "Degree and Major",
      "school": "School Name",
      "location": "City, State",
      "dates": "Year or Year - Year",
      "details": "GPA / honors / relevant coursework if present, else empty string"
    }
  ],
  "skills": ["Skill 1", "Skill 2", "Skill 3"],
  "certifications": ["Certification 1"],
  "keywords_added": ["keyword1", "keyword2"],
  "target_role": "The exact job title being applied for, as stated in the job description (e.g. 'Senior Data Analyst', 'Software Engineer II'). 2-6 words max.",
  "company_name": "The hiring company or organization name, exactly as it appears in the job description. Empty string if not found."
}"""


def tailor_resume(
    resume_text: str,
    job_description: str,
    api_key: str,
    temperature: float = 0.3,
    preserve_structure: bool = False,
) -> dict:
    """
    Call Claude to tailor the resume to the job description.
    Returns a dict with the structured resume data.
    """
    client = anthropic.Anthropic(api_key=api_key)

    tone = (
        "be conservative, stay close to original language" if temperature < 0.4
        else "be creative with rewording and verb choices" if temperature > 0.6
        else "balanced rewording"
    )
    ps_block = (
        "\n\nSTRUCTURE PRESERVATION MODE IS ACTIVE — this overrides restructuring guidance:\n"
        "- Do NOT change the order of sections, jobs, or bullet points\n"
        "- Do NOT add or remove bullet points — only rephrase existing ones in place\n"
        "- Keep the summary the same length and general structure as the original\n"
        "- You MAY add implied skills and new entries to the Skills section\n"
        "- Weave keywords into existing bullets only where natural, without changing bullet count or order\n"
        "- Preserve the candidate's voice and phrasing as much as possible\n"
    ) if preserve_structure else ""

    user_message = (
        f"Here is the candidate's current resume:\n\n<resume>\n{resume_text}\n</resume>\n\n"
        f"Here is the job description to tailor the resume for:\n\n"
        f"<job_description>\n{job_description}\n</job_description>\n\n"
        f"Temperature setting: {temperature:.2f} ({tone})"
        f"{ps_block}\n\n"
        "Please tailor this resume to the job description following all the rules in your instructions. "
        "Return ONLY the JSON object, nothing else."
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        temperature=temperature,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if Claude wrapped it
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON: {e}\n\nRaw output:\n{raw[:500]}")
