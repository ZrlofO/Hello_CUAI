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


def explain_job_fit(cv_skills, job_skills, similarity):
    matched = [skill for skill in job_skills if skill in cv_skills]
    missing = [skill for skill in job_skills if skill not in cv_skills]
    reasons = []
    if matched:
        reasons.append(f"일치 역량: {', '.join(matched[:4])}")
    if similarity > 0.18:
        reasons.append("CV 문맥과 공고 설명의 유사도가 높습니다.")
    if not reasons:
        reasons.append("직무 키워드가 일부 겹치지만 증거 보강이 필요합니다.")
    gaps = [GAP_RECOMMENDATIONS.get(skill, f"{skill} 역량을 증명할 결과물을 추가하세요.") for skill in missing[:3]]
    if not gaps:
        gaps = ["성과 수치, 배포 링크, 협업 역할을 더 선명하게 적으면 fit이 올라갑니다."]
    return reasons, gaps


def rank_jobs_for_cv(cv_text, jobs, target_role):
    cv_vector = vectorize(f"{target_role} {cv_text}")
    cv_skills = extract_profile_skills(cv_text)
    ranked = []
    for job in jobs:
        document = job_document(job)
        job_vector = vectorize(document)
        job_skills = list(dict.fromkeys([*job.get("skills", []), *extract_profile_skills(document)]))
        similarity = cosine_similarity(cv_vector, job_vector)
        overlap = len(set(cv_skills) & set(job_skills)) / max(len(set(job_skills)), 1)
        title_bonus = 0.12 if target_role and any(token in document.lower() for token in tokenize(target_role)) else 0
        score = round(min(98, max(45, 58 + similarity * 55 + overlap * 26 + title_bonus * 100)))
        reasons, gaps = explain_job_fit(cv_skills, job_skills, similarity)
        ranked_job = dict(job)
        ranked_job["fit"] = score
        ranked_job["similarity"] = round(similarity, 3)
        ranked_job["matchedSkills"] = [skill for skill in job_skills if skill in cv_skills]
        ranked_job["missingSkills"] = [skill for skill in job_skills if skill not in cv_skills][:4]
        ranked_job["fitReasons"] = reasons
        ranked_job["gaps"] = gaps
        ranked.append(ranked_job)
    return sorted(ranked, key=lambda item: item["fit"], reverse=True)


def build_cv_summary(cv_text, target_role):
    skills = extract_profile_skills(cv_text)
    proof_terms = [
        "research intern", "intern", "accepted", "publication", "conference", "paper", "manuscript",
        "award", "prize", "scholarship", "hackathon", "contest", "leaderboard", "논문", "수상", "인턴", "해커톤",
    ]
    project_terms = ["project", "research", "developed", "designed", "evaluated", "pipeline", "model", "프로젝트", "개발", "분석", "모델"]
    proof_count = count_keyword_hits(cv_text, proof_terms)
    strengths = []
    gaps = []

    if skills:
        strengths.append(f"확인된 핵심 역량: {', '.join(skills[:8])}")
    if count_keyword_hits(cv_text, ["research intern", "kaist", "lab", "advisor"]):
        strengths.append("리서치 인턴 경험이 있어 AI 연구/개발 인턴 포지션에서 신뢰도가 높습니다.")
    if count_keyword_hits(cv_text, ["accepted", "publication", "conference", "paper", "manuscript"]):
        strengths.append("논문·학회 실적이 있어 연구 역량을 외부 결과로 증명하고 있습니다.")
    if count_keyword_hits(cv_text, ["award", "prize", "scholarship", "leaderboard", "hackathon", "contest"]):
        strengths.append("수상·장학·대회 성과가 있어 외부 검증 근거가 충분합니다.")
    if count_keyword_hits(cv_text, project_terms):
        strengths.append("프로젝트와 연구 경험을 공고 요구역량에 맞춰 재배치하기 좋습니다.")

    if not count_keyword_hits(cv_text, ["github", "code", "repository", "demo", "deploy", "open source", "open-source"]):
        gaps.append("연구 성과는 강하지만 코드/데모/GitHub 링크가 약하면 구현 역량 전달력이 떨어질 수 있습니다.")
    if not count_keyword_hits(cv_text, ["latency", "throughput", "accuracy", "benchmark", "flops", "speed", "performance"]):
        gaps.append("AI 인턴 지원에서는 성능 지표, latency, benchmark 같은 정량 결과를 더 앞에 배치하면 좋습니다.")
    if not count_keyword_hits(cv_text, ["production", "service", "api", "deployment", "docker", "cloud"]):
        gaps.append("산업체 개발 인턴을 노린다면 연구 외에 배포/서비스화 경험을 보강하면 fit이 올라갑니다.")
    if len(cv_text) < 500:
        gaps.append("CV 텍스트가 짧습니다. 성과 수치, 사용 기술, 결과 링크를 더 넣어야 정확도가 올라갑니다.")

    return {
        "targetRole": target_role or "목표 직무 미입력",
        "extractedCharacters": len(cv_text),
        "skills": skills,
        "strengths": strengths or ["목표 직무를 더 구체화하면 강점 포지셔닝이 선명해집니다."],
        "gaps": gaps or ["외부 검증은 충분합니다. 이제 목표 공고별 요구 역량 순서에 맞춰 CV 문장을 재배치하세요."],
    }


def count_keyword_hits(text, keywords):
    return sum(1 for keyword in keywords if keyword_matches(text, keyword))


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
            self.send_json(
                {
                    "source": "pdf" if filename else "manual",
                    "filename": filename,
                    "summary": build_cv_summary(cv_text, target_role) | {"pdf": pdf_meta},
                    "rankedJobs": ranked_jobs[:6],
                }
            )
        except (json.JSONDecodeError, ValueError):
            self.send_json({"error": "요청 형식이 올바르지 않습니다.", "rankedJobs": []}, status=400)
        except (urllib.error.URLError, TimeoutError, ElementTree.ParseError):
            ranked_jobs = rank_jobs_for_cv(cv_text, FALLBACK_JOBS, target_role)
            self.send_json(
                {
                    "source": "fallback",
                    "filename": filename,
                    "summary": build_cv_summary(cv_text, target_role) | {"pdf": pdf_meta},
                    "rankedJobs": ranked_jobs[:6],
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
