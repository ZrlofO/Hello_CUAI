# HICAREER

CV/Resume를 분석해 강점과 보완점을 찾고, 전문 Support Agent의 검토 결과를 바탕으로 채용공고를 추천하는 AI 커리어 분석 서비스입니다.

## 주요 흐름

1. PDF 또는 수동 입력으로 CV metadata를 생성합니다.
2. 사용자가 metadata와 선호 정보를 확인·수정합니다.
3. Leading Agent는 외부 합격 사례나 채용공고를 사전 조사하지 않습니다. 좋은 CV/Resume의 품질 기준을 prompt로 주입하고 Support Agent의 검토 범위를 정합니다.
4. Project & Career Experience, Leadership & Contribution, Language & Credential, CV Positioning & Expression Support Agent가 병렬로 CV를 검토합니다.
5. Support 결과를 종합한 뒤 해당 결과를 기준으로 채용공고 최대 10개를 추천합니다.
6. Leading Agent가 Support 결과와 추천 공고를 최종 리포트로 정리합니다.

## CV 품질 기준

기준은 [`agent_prompts/cv_quality_criteria.md`](agent_prompts/cv_quality_criteria.md)에 관리합니다.

- 목표 직무 적합성
- 구체적인 근거와 정량 성과
- 경험 간 일관된 narrative
- 이해하기 쉬운 맥락과 구조
- Action + Method + Scope + Result 형태의 bullet
- 관련성 25점, 근거·정량화 25점 등 100점 기준

사용자 metadata에 없는 경험·성과·수치·자격을 임의로 추가하지 않습니다.

## 실행

```bash
python3 -m pip install -r requirements.txt
PORT=4173 python3 server.py
```

브라우저에서 다음 주소로 접속합니다.

```text
http://localhost:4173/diagnosis.html
```

PDF metadata 추출과 Agent 분석에는 `OPENAI_API_KEY`가 필요합니다.

```bash
OPENAI_API_KEY="your_api_key_here" PORT=4173 python3 server.py
```

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
$env:PORT="4173"
python server.py
```

## 채용공고 추천

채용공고 후보는 서버가 수집한 후보 목록을 사용하며, Support Agent의 weakness 및 보완 방향이 끝난 뒤 추천합니다. 추천 결과는 Support 결과와 연결된 추천 이유를 포함하고 최대 10개까지 화면에 표시합니다.

외부 검색·출처 정책은 [`retrieval_source_registry.json`](retrieval_source_registry.json)에서 관리합니다.

## 주요 파일

- `server.py`: PDF 입력, metadata 처리, Agent orchestration, 채용공고 추천 API
- `script.js`: metadata 편집기, 실시간 Agent 결과, 추천 공고 화면
- `styles.css`: 화면 스타일
- `agent_prompts/`: Leading, Support, JSON 처리 및 CV 품질 기준 prompt
- `metadata_schema.json`: metadata 구조

## 주의사항

- API key를 Git에 커밋하지 마세요.
- 추천 공고의 실제 모집 상태와 마감일은 원문 링크에서 최종 확인해야 합니다.
- 분석 결과는 커리어 준비를 위한 참고 자료이며 합격을 보장하지 않습니다.
