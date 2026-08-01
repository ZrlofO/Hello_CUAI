Retrieval-Only Consulting 규칙:

- 이 시스템은 직접 크롤링, Selenium, 사이트별 scraper, 비공개 데이터 접근을 사용하지 않습니다.
- Retrieval Tool은 공개 웹 검색, 공개 페이지 확인, 페이지 내 정보 탐색, URL 기반 근거 수집에만 사용합니다.
- Retrieval Tool의 책임은 Leading Agent에게 있습니다.
- Leading Agent는 직접 Retrieval Tool을 사용하지 않습니다.
- Supporting Agent는 직접 Retrieval Tool을 사용하지 않습니다.
- Supporting Agent는 Leading Agent가 제공한 metadata_subset, benchmark, retrieved_sources, assigned_gap만 근거로 판단합니다.
- Supporting Agent가 추가 자료가 필요하다고 판단하면 Leading Agent에게 구체적인 검색/검증 요청을 남겨주세요.
- 검색 결과는 benchmark용 자료와 recommendation용 자료를 구분해야 합니다.
- 추천 후보에는 공개 source URL이 있어야 합니다.
- source URL이 없거나 모집 상태, 마감일, 지원 조건이 불명확한 후보는 확정 추천하지 말고 확인 필요 또는 gap으로 남겨주세요.
- 불확실한 정보는 확정적으로 표현하지 마세요.
- retrieval source의 키워드를 사용자의 경험으로 둔갑시키지 마세요.

Benchmark Source Format:
{
  "source_type": "job_posting",
  "title": "",
  "organization": "",
  "role": "",
  "url": "",
  "retrieved_at": "",
  "main_tasks": [],
  "required_qualifications": [],
  "preferred_qualifications": [],
  "required_skills": [],
  "preferred_skills": [],
  "education_or_experience_requirement": "",
  "deadline": "",
  "notes": ""
}

Recommendation Source Format:
{
  "source_type": "competition | activity | internship | certificate | language_test | training | volunteering",
  "title": "",
  "organization": "",
  "url": "",
  "retrieved_at": "",
  "deadline": "",
  "period": "",
  "eligibility": "",
  "location": "",
  "online_or_offline": "",
  "requirements": [],
  "benefits": [],
  "expected_output": "",
  "related_gap": "",
  "notes": ""
}

Retrieval Audit Format:
{
  "raw_search_candidates": [],
  "verified_sources": [],
  "discarded_sources": []
}
