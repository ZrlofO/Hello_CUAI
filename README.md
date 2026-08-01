# HICAREER

HICAREER는 CV를 분석해 취업 준비생의 강점, 보완점, 추천 활동, 지원 기업 방향을 제안하는 한국어 AI 커리어 에이전트 웹사이트 프로토타입입니다.

## 핵심 컨셉

- CV 기반 강점·약점 진단
- 봉사활동, 대외활동, 공모전 등 보완 활동 추천
- 강점이 잘 드러나는 기업·산업군 추천
- 네이비 패브릭 이미지에서 영감을 받은 프리미엄 컬러 테마

## 실행

정적 파일만 확인하려면 브라우저에서 `index.html`을 열면 됩니다.

채용 공고 실시간 검색까지 함께 확인하려면 `python3 -m http.server`가 아니라 다음처럼 백엔드 서버로 실행해야 합니다.

```bash
cd /root/hicareer
python3 -m pip install -r requirements.txt
PORT=4173 python3 server.py
```

브라우저에서 `http://localhost:4173`으로 접속합니다.

## 채용 공고 연동 방향

홈의 인기 채용 공고 섹션은 검색창 입력값으로 `/api/jobs/popular?limit=12&keyword=...`를 실시간 호출하고, 백엔드가 없거나 외부 사이트 요청이 실패하면 샘플 데이터로 표시됩니다.
`server.py`는 기능 검증을 위해 사람인/잡코리아 검색 페이지를 서버에서 읽어오고, 실패 시 Work24 API 또는 샘플 데이터로 fallback합니다.
실서비스에서는 각 서비스의 공식 API/제휴 방식과 이용약관을 확인한 뒤 서버 라우트에서 통합하는 구조를 권장합니다.

권장 호출 전략:

- 홈에서는 인기/최신 공고 6개만 조회
- 동일 조건은 10분 캐싱
- 상세 설명 전문보다 회사, 직무, 요구역량, 마감일, 링크만 사용
- 진단 페이지에서는 목표 직무 기준 공고 5~10개만 분석

### Work24 API 설정

1. Work24 OpenAPI에서 채용정보 API 인증키를 발급받습니다.
2. `.env.example`을 참고해 `WORK24_AUTH_KEY` 환경변수를 설정합니다.
3. `python3 server.py`로 실행하면 홈에서 `/api/jobs/popular`를 통해 공고를 불러옵니다.

예시:

```bash
WORK24_AUTH_KEY=발급받은_키 python3 server.py
```

### 사람인/잡코리아 기능 검증 모드

`server.py`는 기본적으로 검색 키워드에 맞춰 사람인과 잡코리아 검색 결과를 먼저 시도합니다.
사이트 HTML 구조 변경, 차단, 네트워크 실패가 발생하면 Work24 또는 샘플 데이터로 자동 대체됩니다.

예시:

```bash
python3 server.py
# http://localhost:8080/api/jobs/popular?limit=6&keyword=AI%20인턴
```

## CV 분석 및 fit ranking MVP

`/api/analyze-cv`는 PDF 업로드 또는 질문형 입력 텍스트를 받아 현재 채용공고와 비교합니다.

동작 흐름:

1. PDF 업로드 시 서버에서 텍스트를 추출합니다.
2. 목표 직무 키워드로 사람인/잡코리아 공고를 검색합니다.
3. CV 텍스트와 공고 문서를 토큰 벡터로 변환합니다.
4. cosine similarity와 기술스택 overlap을 합쳐 fit score를 계산합니다.
5. 추천 이유, 부족한 증거, 보완 액션을 함께 반환합니다.

현재 PDF 추출은 `pypdf`를 우선 사용해 전체 페이지 텍스트를 읽고, 실패하면 내장 fallback 추출기를 사용합니다. 스캔 이미지 PDF는 Affinda 또는 OCR API를 연결하면 개선할 수 있습니다.

### 자동 핵심 표현 추출

CV와 채용공고 ranking은 더 이상 미리 정한 기술 후보 목록에만 맞추지 않습니다.
서버는 CV 텍스트와 공고 문서에서 n-gram 기반 핵심 표현을 자동 추출하고, 문서 유사도와 핵심 표현 overlap을 함께 사용해 fit score를 계산합니다.
고정 키워드 사전은 공고 카드의 보조 분류/fallback에만 사용합니다.


## LLM 리포트 옵션

`OPENAI_API_KEY`를 설정하면 `/api/analyze-cv`가 retrieval/ranking 결과를 OpenAI Responses API에 전달해 더 자연스러운 한국어 리포트를 생성합니다.
키가 없거나 호출이 실패하면 기존 로컬 agent 리포트로 자동 fallback합니다.

```bash
cd /root/hicareer
export OPENAI_API_KEY="your_api_key_here"
export OPENAI_MODEL="gpt-5.6-luna"
PORT=4173 python3 server.py
```

주의: API 키는 절대 GitHub에 커밋하지 마세요. 이미 채팅이나 로그에 노출된 키는 OpenAI dashboard에서 revoke/rotate하는 것을 권장합니다.
