const hasPdfButton = document.querySelector("#hasPdfButton");
const noPdfButton = document.querySelector("#noPdfButton");
const backFromPdf = document.querySelector("#backFromPdf");
const backFromManual = document.querySelector("#backFromManual");
const pdfMode = document.querySelector("#pdfMode");
const manualMode = document.querySelector("#manualMode");
const cvFile = document.querySelector("#cvFile");
const fileName = document.querySelector("#fileName");
const pdfRoleInput = document.querySelector("#pdfRoleInput");
const extractButton = document.querySelector("#extractButton");
const analyzeButton = document.querySelector("#analyzeButton");
const resultCard = document.querySelector("#resultCard");
const roleInput = document.querySelector("#roleInput");
const educationInput = document.querySelector("#educationInput");
const projectInput = document.querySelector("#projectInput");
const workInput = document.querySelector("#workInput");
const activityInput = document.querySelector("#activityInput");
const strengthInput = document.querySelector("#strengthInput");
const extraInput = document.querySelector("#extraInput");
const manualInputs = [roleInput, educationInput, projectInput, workInput, activityInput, strengthInput, extraInput];

function getManualText() {
  return manualInputs
    .map((input) => input?.value.trim())
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
  analyzeButton.classList.toggle("hidden", !isManual);
}

function resetInputMode() {
  hasPdfButton.classList.remove("active");
  noPdfButton.classList.remove("active");
  pdfMode.classList.remove("active");
  manualMode.classList.remove("active");
  analyzeButton.classList.add("hidden");
}

function renderMessage(label, title, items = []) {
  resultCard.innerHTML = `
    <span class="result-label">${label}</span>
    <h3>${title}</h3>
    ${items.length ? `<ul>${items.map((item) => `<li>${item}</li>`).join("")}</ul>` : ""}
  `;
}

function getCompletedActions() {
  try {
    return JSON.parse(localStorage.getItem("hicareer-completed-actions")) || {};
  } catch {
    return {};
  }
}

function setCompletedAction(id, done) {
  const completed = getCompletedActions();
  completed[id] = done;
  localStorage.setItem("hicareer-completed-actions", JSON.stringify(completed));
}

function renderList(items) {
  return items?.length ? `<ul>${items.map((item) => `<li>${item}</li>`).join("")}</ul>` : "";
}

function renderLlmReport(report) {
  if (!report || report.error) {
    return report?.error ? `<p class="extract-meta">LLM 리포트 fallback: ${report.error}</p>` : "";
  }

  return `
    <div class="llm-report">
      <span class="result-label">LLM Career Report</span>
      <h4>${report.headline || "CV와 공고 fit을 요약했습니다."}</h4>
      ${report.cvSummary ? `<p>${report.cvSummary}</p>` : ""}
      <div class="llm-grid">
        <article>
          <h5>강점</h5>
          ${renderList(report.strengths || [])}
        </article>
        <article>
          <h5>보완할 증거</h5>
          ${renderList(report.evidenceGaps || [])}
        </article>
      </div>
      <div class="llm-section">
        <h5>공고별 fit 해석</h5>
        ${(report.jobFitNotes || [])
          .map(
            (item) => `
              <article>
                <strong>${item.title}</strong>
                <p>${item.fitReason}</p>
                <small>${item.risk}</small>
              </article>
            `,
          )
          .join("")}
      </div>
      <div class="llm-section">
        <h5>추천 액션</h5>
        ${(report.recommendedActions || [])
          .map(
            (item) => `
              <article>
                <strong>${item.title}</strong>
                <p>${item.why}</p>
                <small>${item.timeEstimate}</small>
              </article>
            `,
          )
          .join("")}
      </div>
      ${report.profileUpdatePrompt ? `<p class="profile-prompt">${report.profileUpdatePrompt}</p>` : ""}
    </div>
  `;
}

function renderAgent(agent) {
  if (!agent) return "";
  const completed = getCompletedActions();
  return `
    <div class="agent-section">
      <div class="agent-header">
        <span class="result-label">Agent Execution</span>
        <h4>HICAREER Agent가 실행한 단계</h4>
      </div>
      <div class="agent-trace">
        ${agent.trace
          .map(
            (step) => `
              <article>
                <span>${step.step}</span>
                <strong>${step.label}</strong>
                <p>${step.detail}</p>
              </article>
            `,
          )
          .join("")}
      </div>
      <div class="agent-grid">
        <article>
          <h4>공통 요구 표현</h4>
          <div class="skill-row">${agent.commonRequirements.map((item) => `<span>${item}</span>`).join("")}</div>
        </article>
        <article>
          <h4>증거 gap</h4>
          ${renderList(agent.evidenceGaps)}
        </article>
      </div>
      <div class="opportunity-list">
        <h4>gap을 채울 추천 활동</h4>
        ${agent.opportunities
          .map(
            (item) => `
              <article class="opportunity-mini-card">
                <div class="job-card-top">
                  <span class="fit high">Fit ${item.fit}</span>
                  <span class="deadline">${item.deadline}</span>
                </div>
                <strong>${item.title}</strong>
                <p>${item.why}</p>
                <small>${item.source} · 예상 ${item.duration}</small>
                <a href="${item.url}" target="_blank" rel="noopener noreferrer">확인하기</a>
              </article>
            `,
          )
          .join("")}
      </div>
      <div class="weekly-plan">
        <h4>이번 주 액션</h4>
        ${agent.weeklyPlan
          .map(
            (action) => `
              <label class="action-check">
                <input type="checkbox" data-action-id="${action.id}" ${completed[action.id] ? "checked" : ""} />
                <span>
                  <strong>${action.title}</strong>
                  <small>${action.source} · ${action.duration}</small>
                  <em>${action.reason}</em>
                </span>
              </label>
            `,
          )
          .join("")}
      </div>
    </div>
  `;
}

function bindActionChecks() {
  document.querySelectorAll("[data-action-id]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      setCompletedAction(checkbox.dataset.actionId, checkbox.checked);
    });
  });
}

function renderLoading() {
  resultCard.innerHTML = `
    <span class="result-label">분석 중</span>
    <h3>CV를 읽고 현재 채용공고와 fit을 계산하고 있어요.</h3>
    <div class="analysis-loading"><span></span><span></span><span></span></div>
  `;
}

async function readJsonResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("실시간 분석 API가 연결되지 않았어요. `python3 server.py`로 실행한 주소에서 다시 열어주세요.");
  }

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "분석에 실패했습니다.");
  }
  return data;
}

function renderAnalysis(data) {
  const summary = data.summary;
  const rankedJobs = data.rankedJobs || [];

  resultCard.innerHTML = `
    <span class="result-label">Retrieval Fit 리포트</span>
    <h3>${summary.targetRole} 기준 추천 공고를 랭킹했습니다.</h3>
    <div class="summary-grid">
      <div><strong>${summary.extractedCharacters}</strong><span>추출 문자</span></div>
      <div><strong>${summary.pdf?.method === "openai_input_file" ? "LLM" : summary.pdf?.pages || 0}</strong><span>정리 방식</span></div>
      <div><strong>${rankedJobs.length}</strong><span>추천 공고</span></div>
    </div>
    <p class="extract-meta">정리 방식: ${summary.pdf?.method || "manual"}</p>
    ${renderLlmReport(data.llmReport)}
    <div class="analysis-block">
      <h4>강점</h4>
      <ul>${summary.strengths.map((item) => `<li>${item}</li>`).join("")}</ul>
    </div>
    <div class="analysis-block">
      <h4>보완할 증거</h4>
      <ul>${summary.gaps.map((item) => `<li>${item}</li>`).join("")}</ul>
    </div>
    ${renderAgent(data.agent)}
    <div class="ranked-jobs">
      <h4>추천 채용공고 ranking</h4>
      ${rankedJobs
        .map(
          (job, index) => `
            <article class="ranked-job-card">
              <div class="job-card-top">
                <span class="fit high">#${index + 1} Fit ${job.fit}</span>
                <span class="deadline">${job.deadline}</span>
              </div>
              <span class="job-source">${job.source || "검색"}</span>
              <h4>${job.title}</h4>
              <p class="company">${job.company}</p>
              <p class="job-meta">${job.location}</p>
              <div class="skill-row">${job.skills.map((skill) => `<span>${skill}</span>`).join("")}</div>
              <ul class="fit-list">
                ${job.fitReasons.map((reason) => `<li>${reason}</li>`).join("")}
              </ul>
              <p class="gap-copy"><strong>보완:</strong> ${job.gaps[0]}</p>
              <a href="${job.url}" target="_blank" rel="noopener noreferrer">공고 보기</a>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
  bindActionChecks();
}

function fillManualFields(fields) {
  if (fields.targetRole && !roleInput.value.trim()) roleInput.value = fields.targetRole;
  educationInput.value = fields.education || educationInput.value;
  projectInput.value = fields.projects || projectInput.value;
  workInput.value = fields.work || workInput.value;
  activityInput.value = fields.activity || activityInput.value;
  strengthInput.value = fields.strength || strengthInput.value;
  extraInput.value = fields.extra || extraInput.value;
}

async function extractPdfToForm() {
  if (cvFile.files.length === 0) {
    renderMessage("PDF 대기 중", "먼저 CV PDF를 업로드해주세요.", ["PDF를 선택하면 텍스트 추출 후 질문 입력칸을 자동으로 채웁니다."]);
    return;
  }

  const formData = new FormData();
  formData.append("cv_file", cvFile.files[0]);
  formData.append("target_role", pdfRoleInput.value.trim());
  renderMessage("PDF 추출 중", "LLM이 PDF를 직접 읽고 입력칸별 bullet point로 정리하고 있어요.", ["정리된 bullet point를 직접 수정한 다음 분석 버튼을 눌러주세요."]);
  extractButton.disabled = true;

  try {
    const response = await fetch("/api/extract-cv", { method: "POST", body: formData });
    const data = await readJsonResponse(response);
    fillManualFields(data.fields || {});
    setInputMode("manual");
    renderMessage("정리 완료", "LLM이 PDF를 읽고 입력칸을 bullet point로 채웠습니다.", [
      "각 입력칸을 확인하고 필요한 부분을 수정한 뒤 분석 버튼을 눌러주세요.",
      `정리 방식: ${data.pdf?.method || "unknown"}`,
    ]);
  } catch (error) {
    renderMessage("추출 실패", error.message, ["OPENAI_API_KEY가 설정되어 있는지 확인하거나 질문 입력으로 직접 작성해주세요."]);
  } finally {
    extractButton.disabled = false;
  }
}

async function analyzeManual() {
  const response = await fetch("/api/analyze-cv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target_role: roleInput.value.trim(),
      cv_text: getManualText(),
    }),
  });
  return readJsonResponse(response);
}

async function renderReport() {
  const isPdfMode = pdfMode.classList.contains("active");
  const isManualMode = manualMode.classList.contains("active");

  if (!isPdfMode && !isManualMode) {
    renderMessage("먼저 선택", "CV PDF가 있는지 먼저 알려주세요.", ["PDF가 있으면 업로드 화면을, 없으면 질문형 스펙 입력창을 열어드립니다."]);
    return;
  }

  if (isPdfMode) {
    renderMessage("먼저 PDF 정리", "PDF를 바로 분석하지 않고 LLM으로 입력칸을 먼저 채웁니다.", ["`LLM으로 PDF 정리해서 입력칸 채우기` 버튼을 누른 뒤 내용을 수정하고 분석해주세요."]);
    return;
  }

  if (isManualMode && !getManualText()) {
    renderMessage("입력 필요", "질문 입력칸을 하나 이상 채워주세요.", ["목표 직무와 프로젝트 경험만 적어도 1차 retrieval fit 분석이 가능합니다."]);
    return;
  }

  renderLoading();
  analyzeButton.disabled = true;

  try {
    const data = await analyzeManual();
    renderAnalysis(data);
  } catch (error) {
    renderMessage("분석 실패", error.message, ["백엔드는 `python3 server.py`로 실행해야 하고, PDF 정리는 OPENAI_API_KEY가 필요합니다."]);
  } finally {
    analyzeButton.disabled = false;
  }
}

hasPdfButton.addEventListener("click", () => setInputMode("pdf"));
noPdfButton.addEventListener("click", () => setInputMode("manual"));
backFromPdf.addEventListener("click", resetInputMode);
backFromManual.addEventListener("click", resetInputMode);
cvFile.addEventListener("change", () => {
  fileName.textContent = cvFile.files[0]?.name || "이력서 또는 CV 파일을 올려주세요.";
});
extractButton?.addEventListener("click", extractPdfToForm);
analyzeButton.addEventListener("click", renderReport);
