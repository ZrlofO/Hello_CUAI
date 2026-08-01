import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
WORK24_AUTH_KEY = os.getenv("WORK24_AUTH_KEY", "")
WORK24_ENDPOINT = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do"
CACHE_TTL_SECONDS = int(os.getenv("JOBS_CACHE_TTL_SECONDS", "600"))

_cache = {"saved_at": 0, "jobs": None}

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


def fetch_work24_jobs(limit):
    if not WORK24_AUTH_KEY:
        return FALLBACK_JOBS[:limit]

    if _cache["jobs"] and time.time() - _cache["saved_at"] < CACHE_TTL_SECONDS:
        return _cache["jobs"][:limit]

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

    _cache["saved_at"] = time.time()
    _cache["jobs"] = jobs
    return jobs[:limit]


class HICareerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == "/api/jobs/popular":
            self.handle_popular_jobs(parsed_url)
            return
        super().do_GET()

    def handle_popular_jobs(self, parsed_url):
        query = urllib.parse.parse_qs(parsed_url.query)
        limit = int(query.get("limit", ["6"])[0])

        try:
            jobs = fetch_work24_jobs(limit)
            self.send_json(jobs)
        except (urllib.error.URLError, TimeoutError, ElementTree.ParseError, ValueError):
            self.send_json(FALLBACK_JOBS[:limit])

    def send_json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
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
