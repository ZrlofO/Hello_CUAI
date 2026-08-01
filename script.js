const pdfTab = document.querySelector("#pdfTab");
const manualTab = document.querySelector("#manualTab");
const pdfMode = document.querySelector("#pdfMode");
const manualMode = document.querySelector("#manualMode");
const switchToManual = document.querySelector("#switchToManual");
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
  tech: ["react", "python", "ai", "데이터", "개발", "분석", "프로젝트", "머신러닝"],
  leadership: ["리더", "운영", "회장", "팀장", "기획", "협업", "멘토"],
  activity: ["봉사", "대외활동", "공모전", "동아리", "서포터즈", "인턴", "수상"],
};

function countMatches(text, keywords) {
  const normalizedText = text.toLowerCase();
  return keywords.filter((keyword) => normalizedText.includes(keyword.toLowerCase())).length;
}

function buildReport(text) {
  const techScore = countMatches(text, keywordGroups.tech);
  const leadershipScore = countMatches(text, keywordGroups.leadership);
  const activityScore = countMatches(text, keywordGroups.activity);

  const strengths = [];
  const improvements = [];
  const companies = [];

  if (techScore >= 2) {
    strengths.push("기술·프로젝트 경험이 선명해서 직무 적합도를 보여주기 좋습니다.");
    companies.push("AI 스타트업", "B2B SaaS", "데이터 기반 플랫폼 기업");
  } else {
    improvements.push("직무 핵심 기술과 프로젝트 성과를 숫자로 보강해보세요.");
  }

  if (leadershipScore >= 2) {
    strengths.push("협업·리더십 경험이 있어 조직 적응력을 어필하기 좋습니다.");
    companies.push("초기 스타트업", "서비스 기획 중심 조직");
  } else {
    improvements.push("팀 프로젝트에서 맡은 역할과 의사결정 경험을 더 구체화하세요.");
  }

  if (activityScore >= 2) {
    strengths.push("외부 활동 근거가 있어 실행력과 관심 분야의 지속성이 보입니다.");
  } else {
    improvements.push("봉사활동, 대외활동, 공모전 중 직무와 연결되는 활동을 1개 이상 추가하면 좋습니다.");
  }

  if (!companies.length) {
    companies.push("직무교육형 인턴십", "신입 채용 연계형 프로그램", "성장형 중소·중견기업");
  }

  return {
    headline:
      activityScore < 2
        ? "경험의 방향은 좋고, 외부 검증 활동을 더하면 설득력이 커져요."
        : "지원 직무와 연결되는 경험이 꽤 탄탄하게 보입니다.",
    strengths,
    improvements,
    companies: [...new Set(companies)],
  };
}

function setMode(mode) {
  const isPdfMode = mode === "pdf";

  pdfTab.classList.toggle("active", isPdfMode);
  manualTab.classList.toggle("active", !isPdfMode);
  pdfMode.classList.toggle("active", isPdfMode);
  manualMode.classList.toggle("active", !isPdfMode);
}

function getManualText() {
  return manualInputs
    .map((input) => input.value.trim())
    .filter(Boolean)
    .join(" ");
}

function renderReport() {
  const isPdfMode = pdfMode.classList.contains("active");
  const hasPdf = cvFile.files.length > 0;

  if (isPdfMode && !hasPdf) {
    setMode("manual");
    resultCard.innerHTML = `
      <span class="result-label">질문 입력으로 전환</span>
      <h3>PDF가 없다면 스펙 질문에 답하면서 진단을 시작할 수 있어요.</h3>
      <ul>
        <li>희망 직무, 프로젝트, 인턴, 대외활동, 강점을 가능한 만큼 채워주세요.</li>
      </ul>
    `;
    return;
  }

  const text = isPdfMode ? `${cvFile.files[0].name} PDF 이력서 업로드 프로젝트 인턴 활동 분석` : getManualText();

  if (!text) {
    resultCard.innerHTML = `
      <span class="result-label">입력 필요</span>
      <h3>스펙 질문 입력칸을 하나 이상 채워주세요.</h3>
      <ul>
        <li>희망 직무, 프로젝트, 인턴, 대외활동, 강점을 질문별로 적어주세요.</li>
      </ul>
    `;
    return;
  }

  const report = buildReport(text);
  const strengths = report.strengths.length
    ? report.strengths
    : ["경험의 원석은 있으니, 직무 키워드와 성과 문장으로 재정리하는 것이 우선입니다."];

  resultCard.innerHTML = `
    <span class="result-label">AI 진단 결과</span>
    <h3>${report.headline}</h3>
    <ul>
      <li><strong>강점:</strong> ${strengths.join(" ")}</li>
      <li><strong>보완:</strong> ${report.improvements.join(" ")}</li>
      <li><strong>추천 기업:</strong> ${report.companies.join(", ")}</li>
      <li><strong>다음 행동:</strong> 링커리어, 위비티, VMS/1365, 캠퍼스픽에서 현재 모집 중인 활동을 직무 키워드로 찾아보세요.</li>
    </ul>
  `;
}

pdfTab.addEventListener("click", () => setMode("pdf"));
manualTab.addEventListener("click", () => setMode("manual"));
switchToManual.addEventListener("click", () => setMode("manual"));
cvFile.addEventListener("change", () => {
  fileName.textContent = cvFile.files[0]?.name || "이력서 또는 CV 파일을 올려주세요.";
});
analyzeButton.addEventListener("click", renderReport);
