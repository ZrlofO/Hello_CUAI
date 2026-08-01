const hasPdfButton = document.querySelector("#hasPdfButton");
const noPdfButton = document.querySelector("#noPdfButton");
const backFromPdf = document.querySelector("#backFromPdf");
const backFromManual = document.querySelector("#backFromManual");
const pdfMode = document.querySelector("#pdfMode");
const manualMode = document.querySelector("#manualMode");
const cvFile = document.querySelector("#cvFile");
const fileName = document.querySelector("#fileName");
const analyzeButton = document.querySelector("#analyzeButton");
const resultCard = document.querySelector("#resultCard");
const manualInputs = [
  document.querySelector("#roleInput"),
  document.querySelector("#educationInput"),
  document.querySelector("#projectInput"),
  document.querySelector("#workInput"),
  document.querySelector("#activityInput"),
  document.querySelector("#strengthInput"),
];

const keywordGroups = {
  ai: ["ai", "머신러닝", "딥러닝", "논문", "모델", "python", "pytorch", "데이터"],
  product: ["기획", "ux", "사용자", "서비스", "pm", "프로덕트", "리서치"],
  engineering: ["react", "개발", "프론트엔드", "백엔드", "api", "오픈소스", "github", "프로젝트"],
  proof: ["인턴", "수상", "공모전", "해커톤", "논문", "오픈소스", "배포", "성과"],
  activity: ["대외활동", "봉사", "동아리", "서포터즈", "운영", "멘토", "리더"],
};

function countMatches(text, keywords) {
  const normalizedText = text.toLowerCase();
  return keywords.filter((keyword) => normalizedText.includes(keyword.toLowerCase())).length;
}

function getManualText() {
  return manualInputs
    .map((input) => input.value.trim())
    .filter(Boolean)
    .join(" ");
}

function setInputMode(mode) {
  const isPdf = mode === "pdf";
  const isManual = mode === "manual";

  hasPdfButton.classList.toggle("active", isPdf);
  noPdfButton.classList.toggle("active", isManual);
  pdfMode.classList.toggle("active", isPdf);
  manualMode.classList.toggle("active", isManual);
}

function resetInputMode() {
  hasPdfButton.classList.remove("active");
  noPdfButton.classList.remove("active");
  pdfMode.classList.remove("active");
  manualMode.classList.remove("active");
}

function detectTrack(text) {
  const aiScore = countMatches(text, keywordGroups.ai);
  const productScore = countMatches(text, keywordGroups.product);
  const engineeringScore = countMatches(text, keywordGroups.engineering);

  if (aiScore >= productScore && aiScore >= engineeringScore && aiScore > 0) {
    return "AI·데이터 직무";
  }

  if (productScore >= engineeringScore && productScore > 0) {
    return "서비스 기획·PM 직무";
  }

  if (engineeringScore > 0) {
    return "소프트웨어 개발 직무";
  }

  return "신입 성장형 직무";
}

function buildReport(text) {
  const track = detectTrack(text);
  const proofScore = countMatches(text, keywordGroups.proof);
  const activityScore = countMatches(text, keywordGroups.activity);
  const aiScore = countMatches(text, keywordGroups.ai);
  const engineeringScore = countMatches(text, keywordGroups.engineering);

  const strengths = [];
  const gaps = [];
  const opportunities = [];
  const companies = [];

  if (aiScore >= 2) {
    strengths.push("AI·데이터 키워드가 있어 연구/분석형 포지셔닝을 만들기 좋습니다.");
    opportunities.push("Kaggle 프로젝트 고도화", "AI 해커톤", "논문 리뷰 스터디");
    companies.push("AI 스타트업", "헬스케어 AI", "데이터 플랫폼 기업");
  }

  if (engineeringScore >= 2) {
    strengths.push("프로젝트와 개발 경험이 보여 실무형 문제 해결력을 어필할 수 있습니다.");
    opportunities.push("오픈소스 PR", "서비스 배포 프로젝트", "개발자 해커톤");
    companies.push("B2B SaaS", "플랫폼 기업", "초기 기술 스타트업");
  }

  if (proofScore < 2) {
    gaps.push("역량을 증명하는 외부 검증 근거가 부족합니다. 수상, 배포, 인턴, 오픈소스처럼 확인 가능한 결과물을 보강하세요.");
  }

  if (activityScore < 2) {
    gaps.push("대외활동·협업 경험이 약하면 조직 적응력 근거가 부족해 보일 수 있습니다. 단, 목표 직무와 연결되는 활동만 추천해야 합니다.");
    opportunities.push("링커리어 직무 연계 대외활동", "1365/VMS 직무 관련 봉사", "위비티 공모전");
  }

  if (!strengths.length) {
    strengths.push("아직 핵심 강점이 흐릿하므로 목표 직무 1개를 정하고 경험을 그 직무 언어로 다시 묶는 것이 우선입니다.");
  }

  if (!gaps.length) {
    gaps.push("기본 증거는 충분합니다. 이제 성과 수치, 역할 범위, 결과물 링크를 더 선명하게 만드는 단계입니다.");
  }

  if (!opportunities.length) {
    opportunities.push("직무교육형 인턴십", "채용 연계 프로젝트", "포트폴리오 리디자인");
  }

  if (!companies.length) {
    companies.push("성장형 중소·중견기업", "직무교육 연계 채용", "신입 온보딩이 강한 스타트업");
  }

  return {
    track,
    strengths,
    gaps,
    opportunities: [...new Set(opportunities)],
    companies: [...new Set(companies)],
  };
}

function renderReport() {
  const isPdfMode = pdfMode.classList.contains("active");
  const isManualMode = manualMode.classList.contains("active");

  if (!isPdfMode && !isManualMode) {
    resultCard.innerHTML = `
      <span class="result-label">먼저 선택</span>
      <h3>CV PDF가 있는지 먼저 알려주세요.</h3>
      <ul>
        <li>PDF가 있으면 업로드 화면을, 없으면 질문형 스펙 입력창을 열어드립니다.</li>
      </ul>
    `;
    return;
  }

  if (isPdfMode && cvFile.files.length === 0) {
    resultCard.innerHTML = `
      <span class="result-label">PDF 대기 중</span>
      <h3>선택은 완료됐어요. 이제 CV PDF를 업로드해주세요.</h3>
      <ul>
        <li>파일이 없다면 “다시 선택” 후 질문 입력 방식으로 진행할 수 있습니다.</li>
      </ul>
    `;
    return;
  }

  const text = isPdfMode ? `${cvFile.files[0].name} PDF 이력서 프로젝트 인턴 오픈소스 활동 분석` : getManualText();

  if (!text) {
    resultCard.innerHTML = `
      <span class="result-label">입력 필요</span>
      <h3>질문 입력칸을 하나 이상 채워주세요.</h3>
      <ul>
        <li>목표 직무와 프로젝트 경험만 적어도 1차 진단이 가능합니다.</li>
      </ul>
    `;
    return;
  }

  const report = buildReport(text);

  resultCard.innerHTML = `
    <span class="result-label">증거 격차 리포트</span>
    <h3>${report.track} 기준으로 다음 성장 전략을 추천합니다.</h3>
    <ul>
      <li><strong>강점:</strong> ${report.strengths.join(" ")}</li>
      <li><strong>부족한 증거:</strong> ${report.gaps.join(" ")}</li>
      <li><strong>현재 찾을 활동:</strong> ${report.opportunities.join(", ")}</li>
      <li><strong>유리한 기업군:</strong> ${report.companies.join(", ")}</li>
      <li><strong>이번 주 액션:</strong> 현재 모집 중인 기회 2개를 고르고, 한 달 안에 CV에 추가할 결과물을 정하세요.</li>
    </ul>
  `;
}

hasPdfButton.addEventListener("click", () => setInputMode("pdf"));
noPdfButton.addEventListener("click", () => setInputMode("manual"));
backFromPdf.addEventListener("click", resetInputMode);
backFromManual.addEventListener("click", resetInputMode);
cvFile.addEventListener("change", () => {
  fileName.textContent = cvFile.files[0]?.name || "이력서 또는 CV 파일을 올려주세요.";
});
analyzeButton.addEventListener("click", renderReport);
