# utils/market_intel.py — Market intelligence: live JD corpus analysis + O*NET skills

import re
import requests
from typing import Optional

_ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"
_ONET_BASE   = "https://services.onetcenter.org/ws"

# ── Curated skill patterns ─────────────────────────────────────────────────────
# Each entry: (display_name, regex_pattern)  — all matched case-insensitively
_SKILLS = [
    # ── Programming languages ──────────────────────────────────────────────────
    ("Python",              r"\bpython\b"),
    ("SQL",                 r"\bsql\b"),
    ("R",                   r"\br\b(?=\s+(?:programming|language|studio|script|package|cran))|\br programming\b|\busing r\b"),
    ("Java",                r"\bjava\b(?!script)"),
    ("JavaScript",          r"\bjavascript\b|\bjs\b"),
    ("Scala",               r"\bscala\b"),
    ("Julia",               r"\bjulia\b"),
    ("MATLAB",              r"\bmatlab\b"),
    ("SAS",                 r"\bsas\b"),
    ("SPSS",                r"\bspss\b"),
    ("Go",                  r"\bgolang\b|\bgo\s+programming\b"),
    ("C / C++",             r"\bc\+\+|\bc programming\b|\blanguage:\s*c\b"),
    # ── Python libraries ──────────────────────────────────────────────────────
    ("Pandas",              r"\bpandas\b"),
    ("NumPy",               r"\bnumpy\b"),
    ("Matplotlib",          r"\bmatplotlib\b"),
    ("Seaborn",             r"\bseaborn\b"),
    ("Plotly",              r"\bplotly\b"),
    ("Scikit-learn",        r"\bscikit[\-\s]?learn\b|\bsklearn\b"),
    ("TensorFlow",          r"\btensorflow\b"),
    ("PyTorch",             r"\bpytorch\b"),
    ("Keras",               r"\bkeras\b"),
    ("SciPy",               r"\bscipy\b"),
    ("XGBoost",             r"\bxgboost\b|\blightgbm\b"),
    # ── BI / Visualization ────────────────────────────────────────────────────
    ("Tableau",             r"\btableau\b"),
    ("Power BI",            r"\bpower\s*bi\b"),
    ("Looker",              r"\blooker\b"),
    ("Qlik",                r"\bqlik\b"),
    ("Metabase",            r"\bmetabase\b"),
    ("Superset",            r"\bapache\s+superset\b|\bsuperset\b"),
    ("Grafana",             r"\bgrafana\b"),
    ("Google Data Studio",  r"\bgoogle\s+data\s+studio\b|\blooker\s+studio\b"),
    ("MicroStrategy",       r"\bmicrostrategy\b"),
    ("Spotfire",            r"\bspotfire\b"),
    # ── Spreadsheets ──────────────────────────────────────────────────────────
    ("Excel",               r"\bexcel\b"),
    ("Google Sheets",       r"\bgoogle\s+sheets\b"),
    ("VBA",                 r"\bvba\b"),
    # ── Databases ─────────────────────────────────────────────────────────────
    ("MySQL",               r"\bmysql\b"),
    ("PostgreSQL",          r"\bpostgresql\b|\bpostgres\b"),
    ("Oracle",              r"\boracle\b(?!\s+cloud)"),
    ("SQL Server",          r"\bsql\s+server\b|\bms\s*sql\b|\bssms\b|\bsql\s+server\b"),
    ("SQLite",              r"\bsqlite\b"),
    ("MongoDB",             r"\bmongodb\b|\bmongo\b"),
    ("Cassandra",           r"\bcassandra\b"),
    ("DynamoDB",            r"\bdynamodb\b"),
    ("Redis",               r"\bredis\b"),
    ("Elasticsearch",       r"\belasticsearch\b|\belastic\s+search\b"),
    ("NoSQL",               r"\bnosql\b"),
    ("Snowflake",           r"\bsnowflake\b"),
    ("Redshift",            r"\bredshift\b"),
    ("BigQuery",            r"\bbigquery\b"),
    ("Databricks",          r"\bdatabricks\b"),
    # ── Cloud ─────────────────────────────────────────────────────────────────
    ("AWS",                 r"\baws\b|\bamazon\s+web\s+services\b"),
    ("Azure",               r"\bazure\b|\bmicrosoft\s+azure\b"),
    ("GCP",                 r"\bgcp\b|\bgoogle\s+cloud\b"),
    ("S3",                  r"\bamazon\s+s3\b|\bs3\s+bucket\b"),
    ("Lambda",              r"\baws\s+lambda\b|\blazda\b|\blambda\s+function\b"),
    # ── Big Data / ETL / Orchestration ────────────────────────────────────────
    ("Spark",               r"\bapache\s+spark\b|\bpyspark\b|\bspark\b"),
    ("Hadoop",              r"\bhadoop\b"),
    ("Kafka",               r"\bapache\s+kafka\b|\bkafka\b"),
    ("Airflow",             r"\bapache\s+airflow\b|\bairflow\b"),
    ("dbt",                 r"\bdbt\b|\bdata\s+build\s+tool\b"),
    ("Fivetran",            r"\bfivetran\b"),
    ("Stitch",              r"\bstitch\s+data\b|\bstitch(?:\s+etl)?\b"),
    ("Talend",              r"\btalend\b"),
    ("SSIS",                r"\bssis\b|\bsql\s+server\s+integration\s+services\b"),
    ("Informatica",         r"\binformatica\b"),
    ("ETL",                 r"\betl\b|\bextract[\s,]+transform[\s,]+load\b"),
    ("Data Pipeline",       r"\bdata\s+pipeline\b"),
    ("Data Warehouse",      r"\bdata\s+warehouse\b|\bdwh\b"),
    ("Data Lake",           r"\bdata\s+lake(?:house)?\b"),
    # ── Analytics concepts ────────────────────────────────────────────────────
    ("Machine Learning",    r"\bmachine\s+learning\b"),
    ("Deep Learning",       r"\bdeep\s+learning\b"),
    ("NLP",                 r"\bnlp\b|\bnatural\s+language\s+processing\b"),
    ("A/B Testing",         r"\ba/?b[\s\-]+test(?:ing)?\b|\bsplit\s+test(?:ing)?\b"),
    ("Hypothesis Testing",  r"\bhypothesis\s+test(?:ing)?\b"),
    ("Statistical Analysis",r"\bstatistical\s+analysis\b|\bstatistics\b"),
    ("Regression",          r"\bregression\s+(?:analysis|model|testing)\b|\blinear\s+regression\b|\blogistic\s+regression\b"),
    ("Classification",      r"\bclassification\s+(?:model|algorithm|task)\b"),
    ("Clustering",          r"\bclustering\b|\bk[\-\s]?means\b"),
    ("Forecasting",         r"\bforecasting\b|\bforecast\s+model\b"),
    ("Time Series",         r"\btime[\-\s]series\b"),
    ("Data Visualization",  r"\bdata\s+visuali[zs]ation\b"),
    ("Business Intelligence",r"\bbusiness\s+intelligence\b|\b(?<!\w)bi(?!\w)\s+(?:tool|report|dashboard|solution|analyst)\b"),
    ("Data Modeling",       r"\bdata\s+model(?:ing)?\b|\bdimensional\s+model(?:ing)?\b"),
    ("Data Governance",     r"\bdata\s+govern(?:ance)?\b"),
    ("Data Quality",        r"\bdata\s+quality\b|\bdata\s+integrity\b"),
    ("Data Profiling",      r"\bdata\s+profil(?:ing)?\b"),
    ("Data Wrangling",      r"\bdata\s+wrangl(?:ing)?\b|\bdata\s+mung(?:ing)?\b|\bdata\s+clean(?:ing)?\b"),
    ("Feature Engineering", r"\bfeature\s+engineer(?:ing)?\b|\bfeature\s+selection\b"),
    ("Predictive Analytics",r"\bpredictive\s+(?:analytics|model(?:ing)?)\b"),
    ("Descriptive Analytics",r"\bdescriptive\s+analytics\b"),
    ("Data Mining",         r"\bdata\s+min(?:ing)?\b"),
    ("Statistical Modeling",r"\bstatistical\s+model(?:ing)?\b"),
    # ── DevOps / Engineering tools ────────────────────────────────────────────
    ("Git",                 r"\bgit\b(?!\s*hub|\s*lab|\s*ops)"),
    ("GitHub",              r"\bgithub\b"),
    ("Docker",              r"\bdocker\b|\bcontaineriz\w+\b"),
    ("Kubernetes",          r"\bkubernetes\b|\bk8s\b"),
    ("Jupyter",             r"\bjupyter\b"),
    ("REST API",            r"\brest(?:ful)?\s+api\b|\brest\s+endpoint\b"),
    ("Linux",               r"\blinux\b|\bunix\b"),
    ("CI/CD",               r"\bci/?cd\b|\bcontinuous\s+integration\b"),
    # ── Marketing / Product analytics ────────────────────────────────────────
    ("Google Analytics",    r"\bgoogle\s+analytics\b|\bga4\b|\bgtm\b"),
    ("Mixpanel",            r"\bmixpanel\b"),
    ("Amplitude",           r"\bamplitude\b"),
    ("Salesforce",          r"\bsalesforce\b|\bsfdc\b"),
    ("Segment",             r"\bsegment\.com\b|\bsegment\s+(?:cdp|analytics|data)\b"),
    # ── Business / Soft skills ────────────────────────────────────────────────
    ("Dashboard",           r"\bdashboard\b"),
    ("KPI",                 r"\bkpi\b|\bkey\s+performance\s+indicator\b"),
    ("Data Storytelling",   r"\bdata\s+storytell(?:ing)?\b|\bstorytell(?:ing)?\b"),
    ("Stakeholder Management", r"\bstakeholder\b"),
    ("Cross-functional",    r"\bcross[\-\s]functional\b"),
    ("Agile",               r"\bagile\b"),
    ("Scrum",               r"\bscrum\b"),
    ("Presentation",        r"\bpresent(?:ation)?\s+skill\b|\bpresenting\s+to\b"),
    ("Communication",       r"\bcommunication\s+skill\b|\bwritten\s+and\s+verbal\b"),
    ("Project Management",  r"\bproject\s+manage(?:ment|r)\b"),
    ("JIRA",                r"\bjira\b|\batlassian\b"),
]


def fetch_jd_corpus(role: str, app_id: str, app_key: str,
                    pages: int = 5, country: str = "us") -> list:
    """
    Fetch up to pages*10 raw JD strings from Adzuna for the given role.
    Returns list of strings (title + full description, untruncated).
    """
    descriptions = []
    for page in range(1, pages + 1):
        try:
            resp = requests.get(
                f"{_ADZUNA_BASE}/{country}/search/{page}",
                params={
                    "app_id":           app_id,
                    "app_key":          app_key,
                    "what":             role,
                    "results_per_page": 10,
                    "content-type":     "application/json",
                },
                timeout=12,
            )
            if not resp.ok:
                break
            for job in resp.json().get("results", []):
                title = job.get("title", "")
                desc  = job.get("description", "")
                if desc:
                    descriptions.append(f"{title}\n{desc}")
        except Exception:
            break
    return descriptions


def _skill_in_text(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, re.IGNORECASE))


def analyze_corpus(jds: list) -> list:
    """
    Analyze a list of JD strings for skill frequency.
    Returns list of dicts sorted by frequency: {skill, count, pct}.
    """
    if not jds:
        return []
    total = len(jds)
    results = []
    for display, pattern in _SKILLS:
        count = sum(1 for jd in jds if _skill_in_text(pattern, jd))
        if count > 0:
            results.append({"skill": display, "count": count, "pct": round(count / total * 100)})
    return sorted(results, key=lambda x: x["count"], reverse=True)


def gap_analysis(resume_text: str, frequencies: list) -> tuple:
    """
    Split skill frequencies into (have, missing) based on resume_text.
    Returns (have: list[dict], missing: list[dict]).
    """
    skill_map = {display: pattern for display, pattern in _SKILLS}
    have, missing = [], []
    for item in frequencies:
        pattern = skill_map.get(item["skill"])
        if pattern and _skill_in_text(pattern, resume_text):
            have.append(item)
        else:
            missing.append(item)
    return have, missing


def fetch_onet_skills(role: str, username: str, password: str) -> Optional[list]:
    """
    Fetch top skills for a role from O*NET Web Services (services.onetcenter.org).
    Requires free credentials from services.onetcenter.org/developer/
    Returns list of {skill, importance} dicts, or None on failure.
    """
    if not username or not password:
        return None
    auth = (username, password)
    headers = {"Accept": "application/json"}
    try:
        # Step 1: find best-matching occupation code
        search = requests.get(
            f"{_ONET_BASE}/online/search",
            params={"keyword": role, "end": 3},
            headers=headers, auth=auth, timeout=10,
        )
        if not search.ok:
            return None
        occupations = search.json().get("occupation", [])
        if not occupations:
            return None
        code = occupations[0]["code"]

        # Step 2: get skills for that occupation
        skills_resp = requests.get(
            f"{_ONET_BASE}/online/occupations/{code}/details/skills",
            headers=headers, auth=auth, timeout=10,
        )
        if not skills_resp.ok:
            return None
        elements = skills_resp.json().get("element", [])
        out = []
        for el in elements:
            val = el.get("score", {}).get("value", 0)
            if val >= 3.0:
                out.append({"skill": el["name"], "importance": round(val, 1)})
        return sorted(out, key=lambda x: x["importance"], reverse=True)
    except Exception:
        return None
