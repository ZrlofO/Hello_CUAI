import html
import io
import json
import math
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
WORK24_AUTH_KEY = os.getenv("WORK24_AUTH_KEY", "")
WORK24_ENDPOINT = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do"
CACHE_TTL_SECONDS = int(os.getenv("JOBS_CACHE_TTL_SECONDS", "600"))
DEFAULT_JOB_KEYWORD = os.getenv("JOB_SEARCH_KEYWORD", "신입 개발 데이터 AI")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
OPENAI_ENDPOINT = "https://api.openai.com/v1/responses"

_cache = {}

FALLBACK_JOBS = [
    {
        "title": "Junior AI Engineer",
        "company": "헬스케어 AI 스타트업",
        "category": "ai",
        "location": "서울 · 하이브리드",
        "deadline": "D-9",
        "fit": 94,
        "skills": ["Python", "LLM", "데이터 전처리"],
        "reason": "프로젝트·논문·해커톤 경험을 강점으로 가져가기 좋은 공고",
        "url": "diagnosis.html",
    },
    {
        "title": "Frontend Developer Intern",
        "company": "B2B SaaS 기업",
        "category": "dev",
        "location": "판교 · 인턴",
        "deadline": "D-12",
        "fit": 89,
        "skills": ["React", "TypeScript", "UI 구현"],
        "reason": "배포 프로젝트와 GitHub 증거를 보여주기 좋은 포지션",
        "url": "diagnosis.html",
    },
    {
        "title": "Data Analyst Assistant",
        "company": "커머스 플랫폼",
        "category": "ai",
        "location": "서울 · 신입",
        "deadline": "D-15",
        "fit": 86,
        "skills": ["SQL", "Dashboard", "A/B Test"],
        "reason": "정량 성과와 문제 정의 역량을 만들기 좋은 공고",
        "url": "diagnosis.html",
    },
    {
        "title": "Product Manager Intern",
        "company": "모바일 서비스 스타트업",
        "category": "product",
        "location": "서울 · 인턴",
        "deadline": "D-7",
        "fit": 82,
        "skills": ["UX Research", "기획", "데이터 해석"],
        "reason": "대외활동·운영 경험을 프로덕트 언어로 바꾸기 좋음",
        "url": "diagnosis.html",
    },
    {
        "title": "Backend Developer Rookie",
        "company": "핀테크 플랫폼",
        "category": "dev",
        "location": "서울 · 신입",
        "deadline": "D-18",
        "fit": 80,
        "skills": ["API", "DB", "협업"],
        "reason": "서버 프로젝트와 장애 해결 경험을 강조하기 좋은 공고",
        "url": "diagnosis.html",
    },
    {
        "title": "Growth Marketer Intern",
        "company": "에듀테크 기업",
        "category": "product",
        "location": "원격 가능",
        "deadline": "D-21",
        "fit": 77,
        "skills": ["콘텐츠", "실험", "분석"],
        "reason": "캠페인·대외활동 경험을 수치 성과로 확장하기 좋음",
        "url": "diagnosis.html",
    },
]


def text_of(item, *names):
    for name in names:
        node = item.find(name)
        if node is not None and node.text:
            return node.text.strip()
    return ""


def infer_category(title):
    lowered = title.lower()
    if any(keyword in lowered for keyword in ["ai", "data", "데이터", "인공지능", "머신러닝", "분석"]):
        return "ai"
    if any(keyword in lowered for keyword in ["개발", "developer", "software", "backend", "frontend", "프론트", "백엔드"]):
        return "dev"
    if any(keyword in lowered for keyword in ["pm", "기획", "product", "서비스", "마케팅", "growth"]):
        return "product"
    return "all"


def infer_skills(title):
    lowered = title.lower()
    skills = []
    candidates = [
        ("Python", ["python", "파이썬", "ai", "인공지능", "데이터"]),
        ("SQL", ["sql", "데이터", "분석"]),
        ("React", ["react", "프론트", "frontend"]),
        ("API", ["api", "백엔드", "backend", "서버"]),
        ("기획", ["기획", "pm", "product"]),
        ("커뮤니케이션", ["운영", "관리", "마케팅", "영업"]),
    ]
    for label, keywords in candidates:
        if any(keyword in lowered for keyword in keywords):
            skills.append(label)
    return skills[:3] or ["직무역량", "협업", "문제해결"]


def normalize_deadline(close_date):
    if not close_date:
        return "상시"
    digits = "".join(char for char in close_date if char.isdigit())
    if len(digits) == 8:
        return f"~{digits[4:6]}.{digits[6:8]}"
    return close_date


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    value = re.sub(r"([A-Z]{2,})([A-Z][a-z])", r"\1 \2", value)
    value = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", value)
    value = re.sub(r"([0-9])([A-Za-z])", r"\1 \2", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -|\n\t")


def absolute_url(base_url, href):
    return urllib.parse.urljoin(base_url, html.unescape(href))


def read_url(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 HICAREER/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
        },
    )
    with urllib.request.urlopen(request, timeout=6) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_deadline(text_block):
    patterns = [
        r'D-\s*\d+',
        r'~\s*\d{1,2}\.\d{1,2}\([^)]*\)',
        r'~\s*\d{1,2}\.\d{1,2}',
        r'오늘마감|내일마감|상시채용|채용시',
    ]
    for pattern in patterns:
        match = re.search(pattern, text_block)
        if match:
            return clean_text(match.group(0))
    return "상세 확인"


def extract_location(text_block):
    regions = [
        "서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종",
        "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주", "원격",
    ]
    match = re.search(r'(' + '|'.join(regions) + r')[가-힣\w\s·,-]{0,24}', text_block)
    if match:
        return clean_text(match.group(0))
    return "지역 확인"


def extract_summary(text_block, title, company):
    cleaned = clean_text(text_block)
    cleaned = cleaned.replace(title, " ").replace(company, " ")
    parts = [part.strip() for part in re.split(r'\s{2,}|\||•|·', cleaned) if part.strip()]
    blocked = ["스크랩", "관심기업", "입사지원", "홈페이지 지원", "즉시지원", "공고 보기"]
    useful = []
    for part in parts:
        if any(word in part for word in blocked):
            continue
        if re.fullmatch(r'D-\s*\d+|~?\d{1,2}\.\d{1,2}.*|\d+분 전.*|\d+일 전.*', part):
            continue
        if 4 <= len(part) <= 90:
            useful.append(part)
    return " · ".join(useful[:2])


def extract_context(html_text, start, end):
    return html_text[max(0, start - 900):min(len(html_text), end + 1200)]


def build_web_job(title, company, url, source, rank, context=""):
    category = infer_category(f"{title} {company} {context}")
    context_text = clean_text(context)
    summary = extract_summary(context, title, company)
    return {
        "title": title or "채용 공고",
        "company": company or source,
        "category": category,
        "location": extract_location(context_text),
        "deadline": extract_deadline(context_text),
        "fit": max(72, 92 - rank * 3),
        "skills": infer_skills(f"{title} {summary}"),
        "reason": summary,
        "url": url,
        "source": source,
    }


def extract_company_near(html_text, start, end):
    before = html_text[max(0, start - 900):start]
    after = html_text[end:min(len(html_text), end + 900)]
    candidates = []
    for pattern in [
        r'class="[^"]*(?:company|corp|name)[^"]*"[^>]*>(.*?)</',
        r'<a[^>]+href="[^"]*(?:company|corp)[^"]*"[^>]*>(.*?)</a>',
        r'<span[^>]*>([^<>]{2,40}(?:주식회사|\(주\)|㈜|유한회사|그룹|테크|랩스|코리아)[^<>]*)</span>',
    ]:
        candidates.extend(clean_text(match) for match in re.findall(pattern, before + after, re.I | re.S))
    return next((candidate for candidate in candidates if candidate and len(candidate) <= 45), "")


def first_match(pattern, text_block):
    match = re.search(pattern, text_block, re.I | re.S)
    if not match:
        return ""
    return clean_text(match.group(1))


def all_matches(pattern, text_block):
    return [clean_text(match) for match in re.findall(pattern, text_block, re.I | re.S) if clean_text(match)]


def scrape_saramin_jobs(keyword, limit):
    query = urllib.parse.urlencode({"searchType": "search", "searchword": keyword})
    base_url = "https://www.saramin.co.kr"
    url = f"{base_url}/zf_user/search/recruit?{query}"
    html_text = read_url(url)
    jobs = []
    seen = set()
    blocks = re.findall(r'<div class="item_recruit"[\s\S]*?(?=<div class="item_recruit"|<div class="common_recruilt_list|$)', html_text)

    for block in blocks:
        link_match = re.search(r'<a[^>]+href="([^"]*(?:/zf_user/jobs/relay/view|/zf_user/jobs/relay/pop-view)[^"]*)"[^>]*(?:title="([^"]+)")?[^>]*>(.*?)</a>', block, re.I | re.S)
        if not link_match:
            continue

        href, title_attr, raw_title = link_match.groups()
        title = clean_text(title_attr or raw_title)
        if len(title) < 4 or title in seen or "스크랩" in title:
            continue

        company = first_match(r'<strong class="corp_name">[\s\S]*?<a[^>]*>(.*?)</a>', block) or extract_company_near(block, 0, len(block))
        deadline = first_match(r'<span class="date">(.*?)</span>', block) or extract_deadline(clean_text(block))
        condition_match = re.search(r'<div class="job_condition">([\s\S]*?)</div>', block, re.I | re.S)
        condition_block = condition_match.group(1) if condition_match else ""
        condition_spans = all_matches(r'<span>([\s\S]*?)</span>', condition_block)
        sectors = all_matches(r'<div class="job_sector">([\s\S]*?)</div>', block)
        condition_text = " ".join(condition_spans) or clean_text(condition_block)
        sector_text = clean_text(" ".join(sectors))
        location = condition_spans[0] if condition_spans else extract_location(condition_text)
        summary_parts = []
        if condition_text:
            summary_parts.append(condition_text)
        if sector_text:
            summary_parts.append(sector_text.replace("등록일", " 등록일"))
        summary = " · ".join(part for part in summary_parts if part)[:140]

        seen.add(title)
        job = build_web_job(title, company, absolute_url(base_url, href), "사람인", len(jobs), block)
        job["deadline"] = deadline
        job["location"] = location
        job["reason"] = summary
        job["skills"] = infer_skills(f"{title} {sector_text}")
        jobs.append(job)
        if len(jobs) >= limit:
            break
    return jobs


def scrape_jobkorea_jobs(keyword, limit):
    query = urllib.parse.urlencode({"stext": keyword})
    base_url = "https://www.jobkorea.co.kr"
    url = f"{base_url}/Search/?{query}"
    html_text = read_url(url)
    jobs = []
    seen = set()

    for match in re.finditer(r'<a[^>]+href="([^"]*(?:/Recruit/GI_Read|/Recruit/Co_Read|/List_GI/)[^"]*)"[^>]*>(.*?)</a>', html_text, re.I | re.S):
        href, raw_title = match.groups()
        title = clean_text(raw_title)
        if len(title) < 4 or title in seen or "즉시지원" in title:
            continue
        seen.add(title)
        context = extract_context(html_text, *match.span())
        company = extract_company_near(html_text, *match.span())
        jobs.append(build_web_job(title, company, absolute_url(base_url, href), "잡코리아", len(jobs), context))
        if len(jobs) >= limit:
            break
    return jobs


def merge_jobs(*job_groups, limit):
    merged = []
    seen = set()
    for group in job_groups:
        for job in group:
            key = f"{job.get('title')}|{job.get('company')}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(job)
            if len(merged) >= limit:
                return merged
    return merged


def normalize_work24_item(item):
    title = text_of(item, "title", "wantedTitle", "recrutPbancTtl") or "채용 공고"
    company = text_of(item, "company", "corpNm", "instNm", "empBusiNm") or "기업명 미공개"
    location = text_of(item, "region", "workRegion", "basicAddr", "workPlc") or "지역 미정"
    close_date = text_of(item, "closeDt", "receiptCloseDt", "pbancEndYmd")
    url = text_of(item, "wantedInfoUrl", "detailUrl", "url") or "diagnosis.html"
    category = infer_category(f"{title} {company}")

    return {
        "title": title,
        "company": company,
        "category": category,
        "location": location,
        "deadline": normalize_deadline(close_date),
        "fit": 78 if category == "all" else 84,
        "skills": infer_skills(title),
        "reason": "현재 채용 시장에서 요구되는 역량을 CV와 비교해보기 좋은 공고",
        "url": url,
    }


def parse_work24_xml(xml_text, limit):
    root = ElementTree.fromstring(xml_text)
    items = root.findall(".//wanted") or root.findall(".//item")
    jobs = [normalize_work24_item(item) for item in items[:limit]]
    return jobs


def fetch_popular_jobs(limit, keyword=DEFAULT_JOB_KEYWORD):
    cache_key = f"web:{keyword}:{limit}"
    cached = _cache.get(cache_key)
    if cached and time.time() - cached["saved_at"] < CACHE_TTL_SECONDS:
        return cached["jobs"][:limit]

    web_jobs = merge_jobs(
        scrape_saramin_jobs(keyword, limit),
        scrape_jobkorea_jobs(keyword, limit),
        limit=limit,
    )
    if web_jobs:
        _cache[cache_key] = {"saved_at": time.time(), "jobs": web_jobs}
        return web_jobs[:limit]

    return fetch_work24_jobs(limit)


def fetch_work24_jobs(limit):
    cache_key = f"work24:{limit}"
    cached = _cache.get(cache_key)
    if cached and time.time() - cached["saved_at"] < CACHE_TTL_SECONDS:
        return cached["jobs"][:limit]

    if not WORK24_AUTH_KEY:
        return FALLBACK_JOBS[:limit]

    params = urllib.parse.urlencode(
        {
            "authKey": WORK24_AUTH_KEY,
            "callTp": "L",
            "returnType": "XML",
            "startPage": "1",
            "display": str(min(max(limit, 1), 20)),
        }
    )
    request = urllib.request.Request(f"{WORK24_ENDPOINT}?{params}", headers={"User-Agent": "HICAREER/1.0"})

    with urllib.request.urlopen(request, timeout=5) as response:
        xml_text = response.read().decode("utf-8", errors="replace")

    jobs = parse_work24_xml(xml_text, limit)
    if not jobs:
        return FALLBACK_JOBS[:limit]

    _cache[cache_key] = {"saved_at": time.time(), "jobs": jobs}
    return jobs[:limit]



SKILL_KEYWORDS = {
    "AI Research": ["artificial intelligence", "ai", "machine learning", "deep learning", "research"],
    "Vision-Language Models": ["vision-language", "vision language", "vlm", "lvlm", "multimodal"],
    "Computer Vision": ["computer vision", "perception", "segmentation", "3d", "bev"],
    "Model Compression": ["pruning", "distillation", "efficient", "token pruning", "compression"],
    "Python": ["python", "파이썬"],
    "SQL": ["sql", "데이터베이스", "database"],
    "React": ["react", "프론트엔드", "frontend"],
    "TypeScript": ["typescript"],
    "LLM": ["llm", "gpt", "agent", "rag", "에이전트", "생성형"],
    "머신러닝": ["머신러닝", "machine learning", "ml", "모델"],
    "딥러닝": ["딥러닝", "deep learning", "pytorch", "tensorflow"],
    "Backend/API": ["api", "백엔드", "backend", "서버"],
    "기획": ["기획", "pm", "product", "프로덕트"],
    "UX": ["ux", "user experience", "사용자", "리서치"],
    "Leadership": ["president", "leader", "leadership", "operating committee", "manager", "led", "운영", "리더"],
    "Open Source": ["open-source", "open source", "opensource", "github", "오픈소스"],
    "Hackathon": ["hackathon", "해커톤"],
    "Publication": ["publication", "accepted", "conference", "paper", "manuscript", "proceedings", "논문"],
}

GAP_RECOMMENDATIONS = {
    "AI Research": "지원 공고의 세부 분야와 가장 가까운 연구/프로젝트 2개를 상단에 배치하세요.",
    "Vision-Language Models": "VLM 관련 성과를 모델, 벤치마크, 지표 중심으로 더 압축해 보여주세요.",
    "Computer Vision": "CV/Perception 프로젝트의 데이터셋과 성능 개선 수치를 명확히 적으세요.",
    "Model Compression": "pruning/distillation 성과를 latency, FLOPs, accuracy trade-off로 정리하세요.",
    "Python": "Python 기반 재현 코드나 GitHub 링크를 함께 제시하세요.",
    "SQL": "SQL 분석 과제나 대시보드 프로젝트로 데이터 근거를 보강하세요.",
    "React": "React로 배포된 포트폴리오 프로젝트 링크를 추가하세요.",
    "TypeScript": "TypeScript 리팩토링 경험을 README에 명확히 남기세요.",
    "LLM": "LLM Agent/RAG 프로젝트에서 데이터, 평가, 실패 분석을 함께 보여주세요.",
    "머신러닝": "모델 학습/평가 지표가 포함된 프로젝트를 추가하세요.",
    "딥러닝": "PyTorch 기반 실험 로그와 결과 비교표를 CV에 연결하세요.",
    "Backend/API": "API 설계/배포 경험을 보여주는 백엔드 프로젝트를 보강하세요.",
    "기획": "문제정의-지표-실험 중심의 서비스 기획 사례를 정리하세요.",
    "UX": "사용자 인터뷰나 UT 결과가 담긴 케이스 스터디를 추가하세요.",
    "Leadership": "리더십 경험을 규모, 예산, 운영 성과 같은 수치로 표현하세요.",
    "Open Source": "오픈소스 기여 링크와 본인의 contribution 범위를 명확히 적으세요.",
    "Hackathon": "해커톤 결과물을 데모 링크나 수상/평가 기준과 함께 보여주세요.",
    "Publication": "대표 논문 2~3개만 목표 직무와 연결해 요약하세요.",
}

def decode_pdf_literal(value):
    value = value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    value = re.sub(r"\\([nrtbf])", " ", value)
    value = re.sub(r"\\[0-7]{1,3}", " ", value)
    return value


def extract_pdf_text_with_fallback(pdf_bytes):
    chunks = []
    raw_streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, re.S)
    candidates = [pdf_bytes]
    for stream in raw_streams:
        stream = stream.strip(b"\r\n")
        try:
            candidates.append(zlib.decompress(stream))
        except zlib.error:
            candidates.append(stream)

    for data in candidates:
        decoded = data.decode("latin-1", errors="ignore")
        literal_strings = re.findall(r"\(((?:[^()]|\\.){2,})\)", decoded)
        for item in literal_strings:
            text = decode_pdf_literal(item)
            if re.search(r"[A-Za-z가-힣]", text):
                chunks.append(text)
        hex_strings = re.findall(r"<([0-9A-Fa-f\s]{8,})>", decoded)
        for item in hex_strings:
            compact = re.sub(r"\s+", "", item)
            try:
                text = bytes.fromhex(compact).decode("utf-16-be", errors="ignore")
            except ValueError:
                continue
            if re.search(r"[A-Za-z가-힣]", text):
                chunks.append(text)
    return clean_text(" ".join(chunks))


def extract_text_from_page(page):
    try:
        return page.extract_text(extraction_mode="layout") or ""
    except TypeError:
        return page.extract_text() or ""


def extract_pdf_text(pdf_bytes):
    for module_name in ("pypdf", "PyPDF2"):
        try:
            module = __import__(module_name)
            reader = module.PdfReader(io.BytesIO(pdf_bytes))
            pages = [extract_text_from_page(page) for page in reader.pages]
            text = clean_text("\n".join(pages))
            if text:
                return {
                    "text": text,
                    "method": module_name,
                    "pages": len(reader.pages),
                }
        except Exception:
            continue

    fallback_text = extract_pdf_text_with_fallback(pdf_bytes)
    return {
        "text": fallback_text,
        "method": "fallback",
        "pages": 0,
    }


def parse_multipart(body, content_type):
    boundary_match = re.search(r"boundary=([^;]+)", content_type)
    if not boundary_match:
        return {}, {}
    boundary = boundary_match.group(1).strip().strip('"').encode()
    fields = {}
    files = {}
    for part in body.split(b"--" + boundary):
        part = part.strip(b"\r\n")
        if not part or part == b"--" or b"\r\n\r\n" not in part:
            continue
        header_bytes, value = part.split(b"\r\n\r\n", 1)
        headers = header_bytes.decode("utf-8", errors="replace")
        name_match = re.search(r'name="([^"]+)"', headers)
        if not name_match:
            continue
        name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]*)"', headers)
        value = value.rstrip(b"\r\n")
        if filename_match and filename_match.group(1):
            files[name] = {"filename": filename_match.group(1), "content": value}
        else:
            fields[name] = value.decode("utf-8", errors="replace")
    return fields, files


def tokenize(text):
    return [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.]{1,}|[가-힣]{2,}", text)]


STOPWORDS = {
    "and", "or", "the", "a", "an", "to", "of", "in", "on", "for", "with", "by", "from", "as", "at", "is", "are",
    "my", "our", "your", "their", "this", "that", "these", "those", "using", "used", "based", "across", "including",
    "experience", "candidate", "present", "expected", "advisor", "author", "authors", "abstract", "email", "phone",
    "kyuan", "oh", "kyuanoh", "chung", "ang", "university", "cau", "cuai", "seoul", "korea", "bumsoo", "kim",
    "award", "paper", "summer", "winter", "conference", "proceedings", "equal", "contribution", "correspondingauthor",
    "under", "review", "submitted", "proceedingsofthe", "th",
    "서울", "경기", "강남구", "영등포구", "성남시", "분당구", "경력무관", "학력무관", "대졸", "계약직", "인턴직", "정규직", "등록일", "수정일", "채용", "공고",
    "시스템통합", "솔루션업체", "전자상거래", "데이터마이닝", "데이터시각화", "앱개발",
}

PHRASE_ALIASES = {
    "vision language": "vision-language",
    "vision language models": "vision-language models",
    "large vision language models": "large vision-language models",
    "open source": "open-source",
    "artificial intelligence": "artificial intelligence",
    "machine learning": "machine learning",
    "deep learning": "deep learning",
}


def normalize_phrase(phrase):
    phrase = clean_text(phrase).lower()
    phrase = phrase.replace("–", "-").replace("—", "-")
    phrase = re.sub(r"[^a-z0-9가-힣+#.\-\s]", " ", phrase)
    phrase = re.sub(r"\s+", " ", phrase).strip()
    return PHRASE_ALIASES.get(phrase, phrase)


def split_glued_function_words(token):
    token = re.sub(r"(diagnosis|distillation|representation|processing|grounding)(and|via|with|for|from|to)$", r"\1 \2", token)
    token = re.sub(r"(research|candidate|developed|designed|conducted)(in|on|for|with)$", r"\1 \2", token)
    return token.split()


def phrase_tokens(text):
    raw_tokens = tokenize(text)
    tokens = []
    for token in raw_tokens:
        tokens.extend(split_glued_function_words(token))
    return [
        token
        for token in tokens
        if token not in STOPWORDS
        and not token.isdigit()
        and 1 < len(token) <= 28
        and not re.fullmatch(r"[a-z]*[0-9][a-z0-9]*", token)
    ]


def extract_keyphrases(text, top_n=12):
    tokens = phrase_tokens(text)
    scores = {}
    for size in (1, 2, 3):
        for index in range(0, max(0, len(tokens) - size + 1)):
            phrase = normalize_phrase(" ".join(tokens[index:index + size]))
            if not phrase or phrase in STOPWORDS:
                continue
            parts = phrase.split()
            if any(part in STOPWORDS for part in parts):
                continue
            if re.search(r"시스템통합|솔루션업체|전자상거래|영등포구|강남구|성남시|분당구", phrase):
                continue
            if "java" in parts and "python" in parts:
                continue
            if "si" in parts:
                continue
            if len(set(parts)) < len(parts):
                continue
            if size == 1 and len(phrase) <= 2:
                continue
            length_bonus = 1 + (size - 1) * 0.55
            technical_bonus = 2.2 if re.fullmatch(r"python|pytorch|llm|rag|agent|sql|react|typescript|머신러닝|딥러닝", phrase) else 1.45 if re.search(r"ai|llm|vlm|vision|language|model|token|pruning|distillation|python|pytorch|react|sql|agent|rag|multimodal|projector|perception|데이터|분석", phrase) else 1
            metadata_penalty = 0.45 if re.search(r"university|conference|award|paper|kyuan|bumsoo|cuai|scholarship", phrase) else 1
            scores[phrase] = scores.get(phrase, 0) + length_bonus * technical_bonus * metadata_penalty

    ranked = sorted(scores.items(), key=lambda item: (item[1], len(item[0])), reverse=True)
    selected = []
    for phrase, score in ranked:
        if any(phrase != chosen and phrase in chosen for chosen in selected):
            continue
        selected.append(phrase)
        if len(selected) >= top_n:
            break
    return selected


def overlap_phrases(left, right):
    left_set = set(left)
    right_set = set(right)
    exact = left_set & right_set
    fuzzy = set()
    for left_phrase in left_set:
        for right_phrase in right_set:
            if left_phrase == right_phrase:
                continue
            if len(left_phrase) >= 5 and len(right_phrase) >= 5 and (left_phrase in right_phrase or right_phrase in left_phrase):
                fuzzy.add(left_phrase if len(left_phrase) <= len(right_phrase) else right_phrase)
    return list(exact | fuzzy)


def evidence_signals(cv_text):
    signals = []
    compact = compact_text(cv_text)
    checks = [
        ("research intern", "리서치 인턴"),
        ("publication", "논문/출판"),
        ("accepted", "논문 accept"),
        ("conference", "학회"),
        ("award", "수상"),
        ("prize", "대회 수상"),
        ("hackathon", "해커톤"),
        ("leaderboard", "리더보드 성과"),
        ("president", "리더십"),
        ("scholarship", "장학"),
        ("github", "GitHub"),
        ("open source", "오픈소스"),
        ("kaist", "KAIST 연구 경험"),
    ]
    for keyword, label in checks:
        if compact_text(keyword) in compact:
            signals.append(label)
    return list(dict.fromkeys(signals))

def compact_text(text):
    return re.sub(r"[^a-z0-9가-힣]+", "", text.lower())


def keyword_matches(text, keyword):
    lowered = text.lower()
    normalized_keyword = keyword.lower()
    compact = compact_text(text)
    compact_keyword = compact_text(keyword)

    if re.fullmatch(r"[a-z0-9+#.]{1,3}", normalized_keyword):
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized_keyword)}(?![a-z0-9])", lowered) is not None

    return normalized_keyword in lowered or bool(compact_keyword and compact_keyword in compact)


def vectorize(text):
    vector = {}
    for token in tokenize(text):
        vector[token] = vector.get(token, 0) + 1
    return vector


def cosine_similarity(left, right):
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(key, 0) for key, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def extract_profile_skills(text):
    skills = []
    for skill, keywords in SKILL_KEYWORDS.items():
        if any(keyword_matches(text, keyword) for keyword in keywords):
            skills.append(skill)
    return skills


def job_document(job):
    return " ".join(
        str(value)
        for value in [
            job.get("title", ""),
            job.get("company", ""),
            job.get("location", ""),
            job.get("deadline", ""),
            job.get("reason", ""),
            " ".join(job.get("skills", [])),
        ]
    )


def explain_job_fit(matched_phrases, missing_phrases, similarity):
    reasons = []
    if matched_phrases:
        reasons.append(f"겹치는 핵심 표현: {', '.join(matched_phrases[:4])}")
    if similarity > 0.18:
        reasons.append("CV 전체 문맥과 공고 설명의 유사도가 높습니다.")
    if not reasons:
        reasons.append("공고와 직접 겹치는 표현이 적어 지원 문장 재구성이 필요합니다.")

    gaps = [f"공고에서 보이는 `{phrase}` 근거를 CV에서 더 명확히 보여주세요." for phrase in missing_phrases[:3]]
    if not gaps:
        gaps = ["성과 수치, 대표 프로젝트 링크, 본인 기여도를 더 선명하게 적으면 fit이 올라갑니다."]
    return reasons, gaps


def rank_jobs_for_cv(cv_text, jobs, target_role):
    cv_vector = vectorize(f"{target_role} {cv_text}")
    cv_phrases = extract_keyphrases(cv_text, top_n=24)
    ranked = []
    for job in jobs:
        document = job_document(job)
        job_vector = vectorize(document)
        job_phrases = extract_keyphrases(document, top_n=14)
        matched_phrases = overlap_phrases(cv_phrases, job_phrases)
        missing_phrases = [phrase for phrase in job_phrases if phrase not in matched_phrases]
        similarity = cosine_similarity(cv_vector, job_vector)
        overlap = len(matched_phrases) / max(len(job_phrases), 1)
        title_bonus = 0.12 if target_role and any(token in document.lower() for token in tokenize(target_role)) else 0
        score = round(min(98, max(45, 56 + similarity * 58 + overlap * 30 + title_bonus * 100)))
        reasons, gaps = explain_job_fit(matched_phrases, missing_phrases, similarity)
        ranked_job = dict(job)
        ranked_job["fit"] = score
        ranked_job["similarity"] = round(similarity, 3)
        ranked_job["skills"] = job_phrases[:5]
        ranked_job["matchedSkills"] = matched_phrases[:6]
        ranked_job["missingSkills"] = missing_phrases[:5]
        ranked_job["fitReasons"] = reasons
        ranked_job["gaps"] = gaps
        ranked.append(ranked_job)
    return sorted(ranked, key=lambda item: item["fit"], reverse=True)


def build_cv_summary(cv_text, target_role):
    keyphrases = extract_keyphrases(cv_text, top_n=14)
    signals = evidence_signals(cv_text)
    strengths = []
    gaps = []

    if keyphrases:
        strengths.append(f"CV에서 자동 추출된 핵심 표현: {', '.join(keyphrases[:8])}")
    if signals:
        strengths.append(f"확인된 외부 증거: {', '.join(signals[:8])}")
    if any("intern" in phrase or "research" in phrase for phrase in keyphrases) or "리서치 인턴" in signals:
        strengths.append("연구/인턴 경험이 목표 직무와 연결될 수 있는 강한 근거입니다.")
    if any(signal in signals for signal in ["논문/출판", "논문 accept", "학회"]):
        strengths.append("논문·학회 실적이 있어 연구 역량을 외부 결과로 증명하고 있습니다.")
    if any(signal in signals for signal in ["수상", "대회 수상", "해커톤", "리더보드 성과", "장학"]):
        strengths.append("수상·대회·장학 성과가 있어 외부 검증 근거가 충분합니다.")

    if not any(signal in signals for signal in ["GitHub", "오픈소스"]):
        gaps.append("코드/GitHub/오픈소스 링크가 약하면 구현 역량 전달력이 떨어질 수 있습니다.")
    if not any(phrase in " ".join(keyphrases) for phrase in ["benchmark", "accuracy", "latency", "performance", "evaluation"]):
        gaps.append("성과를 benchmark, accuracy, latency, performance 같은 정량 표현으로 더 앞에 배치하면 좋습니다.")
    if target_role and "intern" not in compact_text(cv_text) and "인턴" not in cv_text:
        gaps.append("인턴 공고에 맞춰 실무 협업/팀 프로젝트 경험을 더 명확히 보여주세요.")
    if len(cv_text) < 500:
        gaps.append("CV 텍스트가 짧습니다. 성과 수치, 사용 기술, 결과 링크를 더 넣어야 정확도가 올라갑니다.")

    return {
        "targetRole": target_role or "목표 직무 미입력",
        "extractedCharacters": len(cv_text),
        "skills": keyphrases,
        "evidenceSignals": signals,
        "strengths": strengths or ["목표 직무를 더 구체화하면 강점 포지셔닝이 선명해집니다."],
        "gaps": gaps or ["외부 검증은 충분합니다. 이제 목표 공고별 요구 역량 순서에 맞춰 CV 문장을 재배치하세요."],
    }


def count_keyword_hits(text, keywords):
    return sum(1 for keyword in keywords if keyword_matches(text, keyword))

OPPORTUNITY_LIBRARY = [
    {
        "title": "AI 해커톤 또는 공모전 참가",
        "source": "링커리어/위비티 검색 추천",
        "category": "hackathon",
        "duration": "1~3주",
        "deadline": "현재 모집 확인",
        "covers": ["agent", "ai", "python", "model", "evaluation", "hackathon", "공모전"],
        "impact": "외부 검증과 팀 협업 증거를 빠르게 만들 수 있습니다.",
        "url": "https://linkareer.com/list/contest",
    },
    {
        "title": "오픈소스 PR 1개 만들기",
        "source": "GitHub",
        "category": "opensource",
        "duration": "3~7일",
        "deadline": "상시",
        "covers": ["github", "open-source", "code", "python", "api", "react"],
        "impact": "코드 구현력과 외부 협업 증거를 동시에 보강합니다.",
        "url": "https://github.com/explore",
    },
    {
        "title": "RAG/Agent 미니 프로젝트 배포",
        "source": "개인 프로젝트",
        "category": "project",
        "duration": "1~2주",
        "deadline": "상시",
        "covers": ["llm", "agent", "rag", "api", "deployment", "evaluation"],
        "impact": "AI 인턴 공고에서 자주 요구되는 실전 구현 증거를 만들 수 있습니다.",
        "url": "plan.html",
    },
    {
        "title": "Kaggle/데이콘 데이터 분석 제출",
        "source": "데이콘/Kaggle",
        "category": "data",
        "duration": "1~3주",
        "deadline": "현재 대회 확인",
        "covers": ["data", "sql", "python", "benchmark", "performance", "analysis"],
        "impact": "정량 지표와 리더보드 성과를 CV에 추가하기 좋습니다.",
        "url": "https://dacon.io/competitions",
    },
    {
        "title": "직무 연계 봉사/멘토링 활동",
        "source": "1365/VMS",
        "category": "service",
        "duration": "주 2~4시간",
        "deadline": "현재 모집 확인",
        "covers": ["leadership", "communication", "education", "mentoring", "community"],
        "impact": "조직 기여와 커뮤니케이션 증거가 부족할 때만 추천합니다.",
        "url": "https://www.1365.go.kr/vols/main.do",
    },
]


def common_job_requirements(ranked_jobs, top_n=10):
    scores = {}
    for job in ranked_jobs[:8]:
        document = job_document(job)
        for phrase in extract_keyphrases(document, top_n=10):
            scores[phrase] = scores.get(phrase, 0) + 1 + job.get("fit", 0) / 100
    return [phrase for phrase, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_n]]


def detect_evidence_gaps(cv_phrases, common_requirements, evidence):
    matched = overlap_phrases(cv_phrases, common_requirements)
    gaps = [requirement for requirement in common_requirements if requirement not in matched]
    evidence_gap = []
    if not any(signal in evidence for signal in ["GitHub", "오픈소스"]):
        evidence_gap.append("코드/오픈소스 증거")
    if not any(signal in evidence for signal in ["리더보드 성과", "수상", "대회 수상"]):
        evidence_gap.append("외부 평가 성과")
    return matched, list(dict.fromkeys([*gaps[:6], *evidence_gap]))


def score_opportunity(opportunity, gaps, target_role):
    gap_text = " ".join(gaps).lower()
    role_text = target_role.lower()
    coverage = sum(1 for token in opportunity["covers"] if token.lower() in gap_text or token.lower() in role_text)
    urgency = 8 if opportunity["deadline"] != "상시" else 5
    effort = {"3~7일": 9, "1~2주": 8, "1~3주": 7, "주 2~4시간": 6}.get(opportunity["duration"], 6)
    score = min(98, 58 + coverage * 10 + urgency + effort)
    return score


def recommend_opportunities(gaps, target_role):
    ranked = []
    for opportunity in OPPORTUNITY_LIBRARY:
        item = dict(opportunity)
        item["fit"] = score_opportunity(opportunity, gaps, target_role)
        item["why"] = f"보완할 증거 `{gaps[0] if gaps else '직무 적합 증거'}`와 연결됩니다. {opportunity['impact']}"
        ranked.append(item)
    return sorted(ranked, key=lambda item: item["fit"], reverse=True)[:4]


def build_weekly_plan(opportunities, gaps):
    primary = opportunities[:2]
    actions = []
    for index, opportunity in enumerate(primary, start=1):
        actions.append(
            {
                "id": f"week-action-{index}",
                "title": opportunity["title"],
                "source": opportunity["source"],
                "duration": opportunity["duration"],
                "reason": opportunity["why"],
                "done": False,
            }
        )
    actions.append(
        {
            "id": "cv-update",
            "title": "CV 상단 3줄을 목표 공고 언어로 재작성",
            "source": "HICAREER",
            "duration": "30분",
            "reason": f"가장 큰 gap인 `{gaps[0] if gaps else '핵심 요구역량'}`를 먼저 보이게 만듭니다.",
            "done": False,
        }
    )
    return actions


def build_agent_trace(cv_text, target_role, jobs, ranked_jobs, common_requirements, gaps, opportunities):
    return [
        {"step": "CV_READ", "label": "CV PDF/입력 텍스트에서 핵심 증거 추출", "detail": f"{len(cv_text)}자 분석 완료"},
        {"step": "JOB_SEARCH", "label": "목표 직무 채용공고 검색", "detail": f"{target_role or DEFAULT_JOB_KEYWORD} 기준 {len(jobs)}개 후보 수집"},
        {"step": "RETRIEVAL", "label": "CV와 공고 문서 embedding-style ranking", "detail": f"상위 공고: {ranked_jobs[0]['title'] if ranked_jobs else '없음'}"},
        {"step": "REQUIREMENTS", "label": "상위 공고의 공통 요구 표현 추출", "detail": ", ".join(common_requirements[:4])},
        {"step": "GAP", "label": "CV에 부족한 증거 gap 탐지", "detail": ", ".join(gaps[:4]) if gaps else "큰 gap 없음"},
        {"step": "ACTION", "label": "gap을 채울 활동과 이번 주 액션 생성", "detail": f"활동 {len(opportunities)}개 추천"},
    ]


def build_agent_result(cv_text, target_role, jobs, ranked_jobs):
    cv_phrases = extract_keyphrases(cv_text, top_n=18)
    evidence = evidence_signals(cv_text)
    requirements = common_job_requirements(ranked_jobs)
    matched, gaps = detect_evidence_gaps(cv_phrases, requirements, evidence)
    opportunities = recommend_opportunities(gaps, target_role)
    weekly_plan = build_weekly_plan(opportunities, gaps)
    trace = build_agent_trace(cv_text, target_role, jobs, ranked_jobs, requirements, gaps, opportunities)
    return {
        "trace": trace,
        "cvKeyphrases": cv_phrases,
        "commonRequirements": requirements,
        "matchedEvidence": matched,
        "evidenceGaps": gaps,
        "opportunities": opportunities,
        "weeklyPlan": weekly_plan,
    }


def compact_for_prompt(value, max_chars=9000):
    value = clean_text(value)
    return value[:max_chars] + ("..." if len(value) > max_chars else "")


def response_output_text(payload):
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def parse_json_object(text_value):
    try:
        return json.loads(text_value)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text_value)
        if not match:
            raise
        return json.loads(match.group(0))


def build_llm_context(cv_text, summary, ranked_jobs, agent):
    jobs_context = [
        {
            "title": job.get("title"),
            "company": job.get("company"),
            "fit": job.get("fit"),
            "deadline": job.get("deadline"),
            "location": job.get("location"),
            "source": job.get("source"),
            "jobKeyphrases": job.get("skills", []),
            "fitReasons": job.get("fitReasons", []),
            "gaps": job.get("gaps", []),
        }
        for job in ranked_jobs[:5]
    ]
    return {
        "cv_excerpt": compact_for_prompt(cv_text),
        "summary": summary,
        "ranked_jobs": jobs_context,
        "agent": {
            "cvKeyphrases": agent.get("cvKeyphrases", []),
            "commonRequirements": agent.get("commonRequirements", []),
            "matchedEvidence": agent.get("matchedEvidence", []),
            "evidenceGaps": agent.get("evidenceGaps", []),
            "opportunities": agent.get("opportunities", []),
            "weeklyPlan": agent.get("weeklyPlan", []),
        },
    }


def call_openai_llm_report(cv_text, summary, ranked_jobs, agent):
    if not OPENAI_API_KEY:
        return None

    prompt_context = build_llm_context(cv_text, summary, ranked_jobs, agent)
    system_prompt = (
        "You are HICAREER, a Korean career-growth agent. "
        "Use only the provided CV extraction, retrieved job postings, and agent signals. "
        "Do not invent companies, awards, projects, or job requirements. "
        "Write concise Korean. Return JSON only."
    )
    user_prompt = {
        "task": "Generate a commercial-quality CV-to-job fit report and action plan.",
        "output_schema": {
            "headline": "string",
            "cvSummary": "string",
            "strengths": ["string"],
            "evidenceGaps": ["string"],
            "jobFitNotes": [{"title": "string", "fitReason": "string", "risk": "string"}],
            "recommendedActions": [{"title": "string", "why": "string", "timeEstimate": "string"}],
            "weeklyPlan": ["string"],
            "profileUpdatePrompt": "string",
        },
        "context": prompt_context,
    }
    body = json.dumps(
        {
            "model": OPENAI_MODEL,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
            ],
            "max_output_tokens": 1800,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_json_object(response_output_text(payload))


def safe_llm_report(cv_text, summary, ranked_jobs, agent):
    try:
        return call_openai_llm_report(cv_text, summary, ranked_jobs, agent)
    except Exception as exc:
        return {"error": f"LLM report unavailable: {exc.__class__.__name__}"}



def parse_analyze_request(headers, body):
    content_type = headers.get("Content-Type", "")
    if content_type.startswith("multipart/form-data"):
        fields, files = parse_multipart(body, content_type)
        target_role = fields.get("target_role", "")
        pdf_file = files.get("cv_file")
        cv_text = ""
        filename = ""
        pdf_meta = {"method": "manual", "pages": 0}
        if pdf_file:
            filename = pdf_file["filename"]
            extracted = extract_pdf_text(pdf_file["content"])
            cv_text = extracted["text"]
            pdf_meta = {"method": extracted["method"], "pages": extracted["pages"]}
        return cv_text, target_role, filename, pdf_meta

    payload = json.loads(body.decode("utf-8") or "{}")
    return payload.get("cv_text", ""), payload.get("target_role", ""), "", {"method": "manual", "pages": 0}

class HICareerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == "/api/jobs/popular":
            self.handle_popular_jobs(parsed_url)
            return
        super().do_GET()

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == "/api/analyze-cv":
            self.handle_analyze_cv()
            return
        self.send_error(404, "Not found")

    def handle_popular_jobs(self, parsed_url):
        query = urllib.parse.parse_qs(parsed_url.query)
        limit = int(query.get("limit", ["6"])[0])
        keyword = query.get("keyword", [DEFAULT_JOB_KEYWORD])[0]

        try:
            jobs = fetch_popular_jobs(limit, keyword)
            self.send_json(jobs)
        except (urllib.error.URLError, TimeoutError, ElementTree.ParseError, ValueError):
            self.send_json(FALLBACK_JOBS[:limit])

    def handle_analyze_cv(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        cv_text = ""
        target_role = ""
        filename = ""
        pdf_meta = {"method": "unknown", "pages": 0}

        try:
            cv_text, target_role, filename, pdf_meta = parse_analyze_request(self.headers, body)
            if not cv_text.strip():
                self.send_json(
                    {
                        "error": "CV 텍스트를 추출하지 못했습니다. 텍스트 기반 PDF를 업로드하거나 질문 입력을 사용해주세요.",
                        "rankedJobs": [],
                    },
                    status=422,
                )
                return

            keyword = target_role or " ".join(extract_profile_skills(cv_text)[:3]) or DEFAULT_JOB_KEYWORD
            jobs = fetch_popular_jobs(10, keyword)
            ranked_jobs = rank_jobs_for_cv(cv_text, jobs, target_role)
            agent = build_agent_result(cv_text, target_role, jobs, ranked_jobs)
            summary = build_cv_summary(cv_text, target_role) | {"pdf": pdf_meta}
            llm_report = safe_llm_report(cv_text, summary, ranked_jobs, agent)
            self.send_json(
                {
                    "source": "pdf" if filename else "manual",
                    "filename": filename,
                    "summary": summary,
                    "rankedJobs": ranked_jobs[:6],
                    "agent": agent,
                    "llmReport": llm_report,
                }
            )
        except (json.JSONDecodeError, ValueError):
            self.send_json({"error": "요청 형식이 올바르지 않습니다.", "rankedJobs": []}, status=400)
        except (urllib.error.URLError, TimeoutError, ElementTree.ParseError):
            ranked_jobs = rank_jobs_for_cv(cv_text, FALLBACK_JOBS, target_role)
            agent = build_agent_result(cv_text, target_role, FALLBACK_JOBS, ranked_jobs)
            summary = build_cv_summary(cv_text, target_role) | {"pdf": pdf_meta}
            llm_report = safe_llm_report(cv_text, summary, ranked_jobs, agent)
            self.send_json(
                {
                    "source": "fallback",
                    "filename": filename,
                    "summary": summary,
                    "rankedJobs": ranked_jobs[:6],
                    "agent": agent,
                    "llmReport": llm_report,
                }
            )

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", f"public, max-age={CACHE_TTL_SECONDS}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        if self.path.endswith(".js"):
            self.send_header("Content-Type", mimetypes.types_map.get(".js", "application/javascript"))
        super().end_headers()


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), HICareerHandler)
    print(f"HICAREER running at http://{HOST}:{PORT}")
    server.serve_forever()
