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
let liveLaneState = {};

const metadataConfig = {
  education: { label: "교육", fields: { school: "학교", degree: "학위", major: "전공", period: "기간", gpa: "GPA", raw_text: "원문" } },
  projects_and_experience: { label: "프로젝트 및 경험", fields: { title: "제목", type: "유형", period: "기간", organization: "기관/회사", role: "역할", description: "설명", raw_text: "원문" } },
  awards: { label: "수상", fields: { title: "수상명", date: "일자", issuer: "수여기관", related_activity: "관련 활동", description: "설명", raw_text: "원문" } },
  leadership_and_volunteering: { label: "리더십 및 봉사", fields: { title: "제목", type: "유형", period: "기간", organization: "기관", role: "역할", description: "설명", hours: "시간", raw_text: "원문" } },
  languages_and_certificates: { label: "언어 및 자격증", fields: { name: "이름", type: "유형", score_or_level: "점수/등급", issuer: "발급기관", date: "일자", raw_text: "원문" } },
  skills: { label: "기술", fields: { name: "기술명", context: "사용 맥락", raw_text: "원문" } },
  other: { label: "기타", fields: { content: "내용", raw_text: "원문" } },
};
let metadataState = Object.fromEntries(Object.keys(metadataConfig).map((key) => [key, []]));

function createEmptyMetadataItem(category) {
  return Object.fromEntries(Object.keys(metadataConfig[category].fields).map((field) => [field, ""]));
}

function initializeManualMetadata() {
  if (Object.values(metadataState).some((items) => items.length)) return;
  metadataState = Object.fromEntries(Object.keys(metadataConfig).map((category) => [category, [createEmptyMetadataItem(category)]]));
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>\"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '\"': "&quot;" }[char]));
}

function renderMetadataEditor() {
  const container = document.querySelector("#metadataSections");
  if (!container) return;
  container.innerHTML = Object.entries(metadataConfig).map(([category, config]) => `
    <section class="metadata-section">
      <div class="metadata-section-heading"><div><h4>${config.label}</h4><small>${category}</small></div><button type="button" class="text-button add-metadata" data-category="${category}">+ 항목 추가</button></div>
      <div class="metadata-items">
        ${metadataState[category].length ? metadataState[category].map((item, index) => `
          <article class="metadata-item" data-category="${category}" data-index="${index}">
            <div class="metadata-item-heading"><strong>${config.label} ${index + 1}</strong><button type="button" class="text-button remove-metadata">삭제</button></div>
            <div class="metadata-fields">${Object.entries(config.fields).map(([field, label]) => {
              const multiline = ["description", "context", "raw_text", "content"].includes(field);
              return multiline
                ? `<label>${label}<textarea data-metadata-field="${field}" placeholder="${label}">${escapeHtml(item[field])}</textarea></label>`
                : `<label>${label}<input type="text" data-metadata-field="${field}" placeholder="${label}" value="${escapeHtml(item[field])}" /></label>`;
            }).join("")}</div>
          </article>`).join("") : `<p class="metadata-empty">아직 분류된 정보가 없습니다. 원문에 없는 내용은 추가하지 않아도 됩니다.</p>`}
      </div>
    </section>`).join("");
}

function seedMetadataFromFields(fields) {
  if (fields.metadata && typeof fields.metadata === "object") {
    metadataState = Object.fromEntries(Object.keys(metadataConfig).map((key) => [key, Array.isArray(fields.metadata[key]) ? fields.metadata[key] : []]));
    renderMetadataEditor();
    return;
  }

  const split = (value) => String(value || "").split(/\n+/).map((text) => text.replace(/^[-•*]\s*/, "").trim()).filter(Boolean);
  const make = (value, defaults) => split(value).map((text) => ({ ...defaults, description: text, content: text, raw_text: text }));
  metadataState = Object.fromEntries(Object.keys(metadataConfig).map((key) => [key, []]));
  metadataState.education = make(fields.education, { school: "", degree: "", major: "", period: "", gpa: "" });
  metadataState.projects_and_experience = make(fields.projects, { title: "", type: "프로젝트", period: "", organization: "", role: "" });
  metadataState.projects_and_experience.forEach((item) => { item.title = item.description.slice(0, 80); });
  metadataState.leadership_and_volunteering = make(fields.activity, { title: "", type: "", period: "", organization: "", role: "", hours: "" });
  metadataState.awards = make(fields.strength, { title: "", date: "", issuer: "", related_activity: "", description: "" });
  metadataState.skills = split(fields.extra).slice(0, 12).map((text) => ({ name: text, context: "", raw_text: text }));
  metadataState.other = split(fields.extra).slice(12).map((text) => ({ content: text, raw_text: text }));
  renderMetadataEditor();
}

function getMetadata() {
  document.querySelectorAll(".metadata-item").forEach((item) => {
    const category = item.dataset.category;
    const index = Number(item.dataset.index);
    metadataState[category][index] = { ...metadataState[category][index] };
    item.querySelectorAll("[data-metadata-field]").forEach((field) => { metadataState[category][index][field.dataset.metadataField] = field.value.trim(); });
  });
  return metadataState;
}

function getPreferences() {
  return { target_role: document.querySelector("#preferenceRole")?.value.trim() || "", preparation_period: document.querySelector("#preferencePeriod")?.value.trim() || "", additional_user_input: document.querySelector("#preferenceAdditional")?.value.trim() || "" };
}

function getManualText() {
  return Object.values(getMetadata()).flat().map((item) => Object.values(item).filter(Boolean).join(" ")).filter(Boolean).join(" ");
}

function setInputMode(mode) {
  const isPdf = mode === "pdf";
  const isManual = mode === "manual";

  hasPdfButton.classList.toggle("active", isPdf);
  noPdfButton.classList.toggle("active", isManual);
  pdfMode.classList.toggle("active", isPdf);
  manualMode.classList.toggle("active", isManual);
  if (isManual) initializeManualMetadata();
  if (isManual) renderMetadataEditor();
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
  return items?.length ? `<ul>${items.map((item) => `<li>${formatListItem(item)}</li>`).join("")}</ul>` : "";
}


function renderCompactList(items, limit = 3) {
  const visible = (items || []).slice(0, limit);
  if (!visible.length) return "<p class=\"muted-copy\">표시할 항목이 아직 없습니다.</p>";
  const extra = (items || []).length - visible.length;
  return `<ul>${visible.map((item) => `<li>${formatListItem(item)}</li>`).join("")}${extra > 0 ? `<li>외 ${extra}개 항목은 자세히 보기에서 확인</li>` : ""}</ul>`;
}

function plainText(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  return formatListItem(value);
}


function normalizeText(value) {
  return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
}

function getJobNoteFor(job, llmReport) {
  const notes = llmReport?.jobFitNotes || [];
  const jobTitle = normalizeText(job?.title);
  return notes.find((note) => normalizeText(note.title) === jobTitle)
    || notes.find((note) => jobTitle && normalizeText(note.title).includes(jobTitle.slice(0, 18)))
    || null;
}

function getQuickStrengths(data) {
  const llmStrengths = data.llmReport?.strengths || [];
  if (llmStrengths.length) return llmStrengths;
  const reportSummary = data.feedbackLoop?.leadingReport?.summary;
  if (reportSummary) return [reportSummary];
  return data.summary?.strengths || ["입력된 이력서에서 직무와 연결할 수 있는 강점을 정리 중입니다."];
}

function getQuickGaps(data) {
  const llmGaps = data.llmReport?.evidenceGaps || [];
  if (llmGaps.length) return llmGaps;
  const priorityGaps = data.feedbackLoop?.consultResult?.priority_gaps || data.feedbackLoop?.leadingReport?.critical_gaps || [];
  if (priorityGaps.length) return priorityGaps;
  return data.summary?.gaps || ["목표 직무 기준으로 더 보완하면 좋은 경험을 정리 중입니다."];
}

function getQuickActions(data) {
  const reportActions = data.llmReport?.recommendedActions || [];
  if (reportActions.length) return reportActions.map((item) => item.title ? `${item.title}${item.why ? ` — ${item.why}` : ""}${item.timeEstimate ? ` (${item.timeEstimate})` : ""}` : item);
  return data.feedbackLoop?.leadingReport?.next_actions || [];
}

function renderFullList(items) {
  return renderCompactList(items || [], 99);
}

function renderSlideDeck(title, slides = []) {
  const safeSlides = slides.filter(Boolean);
  if (!safeSlides.length) return "";
  const deckId = `deck-${Math.random().toString(36).slice(2, 9)}`;
  return `
    <section class="slide-deck" id="${deckId}" data-current="0">
      <div class="slide-deck-header">
        <div>
          <span class="result-label">자세히 보기</span>
          <h4>${title}</h4>
        </div>
        <div class="slide-controls">
          <button type="button" data-slide-prev aria-label="이전 카드">←</button>
          <span data-slide-count>1 / ${safeSlides.length}</span>
          <button type="button" data-slide-next aria-label="다음 카드">→</button>
        </div>
      </div>
      <div class="slide-window">
        <div class="slide-track">
          ${safeSlides.map((slide) => `<article class="detail-slide">${slide}</article>`).join("")}
        </div>
      </div>
    </section>
  `;
}

function bindSlideDecks() {
  document.querySelectorAll(".slide-deck").forEach((deck) => {
    const track = deck.querySelector(".slide-track");
    const slides = deck.querySelectorAll(".detail-slide");
    const counter = deck.querySelector("[data-slide-count]");
    const update = (next) => {
      const total = slides.length || 1;
      const current = (next + total) % total;
      deck.dataset.current = String(current);
      if (track) track.style.transform = `translateX(-${current * 100}%)`;
      if (counter) counter.textContent = `${current + 1} / ${total}`;
    };
    deck.querySelector("[data-slide-prev]")?.addEventListener("click", () => update(Number(deck.dataset.current || 0) - 1));
    deck.querySelector("[data-slide-next]")?.addEventListener("click", () => update(Number(deck.dataset.current || 0) + 1));
    update(0);
  });
}

function formatListItem(item) {
  if (!item || typeof item !== "object") return escapeHtml(item || "");
  return escapeHtml(
    item.gap
      || item.gap_name
      || item.title
      || item.recommended_action
      || Object.values(item).filter(Boolean).slice(0, 3).join(" · ")
  );
}

function renderLlmReport(report) {
  if (!report) return "";

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

function getConversationRoleClass(agentName) {
  const name = String(agentName || "").toLowerCase();
  if (name.includes("leading")) return "leading";
  if (name.includes("consult")) return "consult";
  return "support";
}

function getConversationToneClass(agentName) {
  const role = getConversationRoleClass(agentName);
  if (role === "leading") return "strategy";
  if (role === "consult") return "decision";
  return "expert";
}

function renderAgentConversationItem(item, index = 0) {
  return `
    <article class="dialogue-turn ${getConversationToneClass(item.from)}">
      <span>${String(index + 1).padStart(2, "0")}</span>
      <div>
        <strong>${item.from} → ${item.to}</strong>
        <p>${item.message}</p>
      </div>
    </article>
  `;
}

function normalizeCalendarDate(value) {
  const text = String(value || "").trim();
  const match = text.match(/(\d{4})[-./](\d{1,2})[-./](\d{1,2})/);
  if (!match) return "";
  const [, year, month, day] = match;
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

function compactCalendarDate(value) {
  return String(value || "").replaceAll("-", "");
}

function parseCalendarTime(value) {
  const text = String(value || "");
  const match = text.match(/(\d{1,2}):(\d{2})/);
  if (!match) return "";
  return `${match[1].padStart(2, "0")}${match[2]}00`;
}

function addOneHour(timeValue) {
  const normalized = parseCalendarTime(timeValue);
  if (!normalized) return "";
  const hour = Math.min(Number(normalized.slice(0, 2)) + 1, 23);
  return `${String(hour).padStart(2, "0")}${normalized.slice(2)}`;
}

function buildGoogleCalendarUrl(item = {}) {
  const date = normalizeCalendarDate(item.date || item.deadline || item.period);
  if (!date || !item.title) return "";
  const compactDate = compactCalendarDate(date);
  const startTime = parseCalendarTime(item.time);
  const endTime = addOneHour(item.time);
  const nextDay = new Date(`${date}T00:00:00`);
  nextDay.setDate(nextDay.getDate() + 1);
  const compactNextDate = compactCalendarDate(nextDay.toISOString().slice(0, 10));
  const dates = startTime ? `${compactDate}T${startTime}/${compactDate}T${endTime}` : `${compactDate}/${compactNextDate}`;
  const details = [
    item.why_on_calendar,
    item.related_gap ? `Related gap: ${item.related_gap}` : "",
    item.source_url ? `Source: ${item.source_url}` : "",
    item.confirmation_required ? "사용자 확인 후 등록하는 일정 초안입니다." : "",
  ].filter(Boolean).join("\n");
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: item.title,
    dates,
    details,
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

function getCalendarViewDate(calendar = []) {
  const datedItem = calendar.find((item) => normalizeCalendarDate(item.date || item.deadline || item.period));
  const normalized = datedItem ? normalizeCalendarDate(datedItem.date || datedItem.deadline || datedItem.period) : "";
  return normalized ? new Date(`${normalized}T00:00:00`) : new Date();
}

function renderMonthCalendar(calendar = []) {
  const viewDate = getCalendarViewDate(calendar);
  const year = viewDate.getFullYear();
  const month = viewDate.getMonth();
  const firstDay = new Date(year, month, 1).getDay();
  const lastDate = new Date(year, month + 1, 0).getDate();
  const eventsByDate = calendar.reduce((accumulator, item) => {
    const date = normalizeCalendarDate(item.date || item.deadline || item.period);
    if (!date) return accumulator;
    accumulator[date] = [...(accumulator[date] || []), item];
    return accumulator;
  }, {});
  const cells = Array.from({ length: Math.ceil((firstDay + lastDate) / 7) * 7 }, (_, index) => {
    const day = index - firstDay + 1;
    if (day < 1 || day > lastDate) return `<span class="month-calendar-cell is-empty" aria-hidden="true"></span>`;
    const date = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const events = eventsByDate[date] || [];
    return `
      <div class="month-calendar-cell ${events.length ? "has-event" : ""}">
        <strong>${day}</strong>
        ${events.slice(0, 2).map((item) => `<span title="${escapeHtml(item.title || "일정 후보")}">${escapeHtml(item.title || "일정 후보")}</span>`).join("")}
        ${events.length > 2 ? `<em>+${events.length - 2}</em>` : ""}
      </div>
    `;
  });

  return `
    <section class="month-calendar" aria-label="일정 캘린더">
      <div class="month-calendar-header">
        <div>
          <span>Calendar</span>
          <strong>${year}년 ${month + 1}월</strong>
        </div>
        <small>검증된 날짜가 있는 일정만 표시합니다.</small>
      </div>
      <div class="month-calendar-weekdays"><span>일</span><span>월</span><span>화</span><span>수</span><span>목</span><span>금</span><span>토</span></div>
      <div class="month-calendar-days">${cells.join("")}</div>
    </section>
  `;
}

function renderCalendarDraft(calendar = []) {
  return `
    <article class="planner-calendar">
      <div class="planner-section-heading">
        <div><span>실행 계획</span><h6>Calendar Draft</h6></div>
        <small>사용자 확인 후 등록</small>
      </div>
      ${renderMonthCalendar(calendar)}
      ${calendar.length ? `
        <div class="calendar-stack">
          ${calendar.map((item) => {
            const displayDate = [item.date, item.time, item.period, item.deadline].filter(Boolean).join(" · ") || "날짜 확인 필요";
            const googleCalendarUrl = buildGoogleCalendarUrl(item);
            return `
              <section class="calendar-draft-card">
                <div class="calendar-date-badge">
                  <span>${escapeHtml(normalizeCalendarDate(item.date || item.deadline || item.period) || "확인 필요")}</span>
                  <strong>${escapeHtml(item.type || "draft")}</strong>
                </div>
                <div>
                  <strong>${escapeHtml(item.title || "일정 후보")}</strong>
                  <p>${escapeHtml(item.why_on_calendar || item.related_gap || "")}</p>
                  <small>${escapeHtml(displayDate)}</small>
                  ${item.confirmation_required ? `<em>사용자 확인 필요: ${escapeHtml(item.confirmation_reason || "원문 일정 확인 필요")}</em>` : ""}
                  <div class="calendar-actions">
                    ${googleCalendarUrl ? `<a href="${escapeHtml(googleCalendarUrl)}" target="_blank" rel="noopener noreferrer">Google Calendar에 추가</a>` : ""}
                    ${item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer">원문 확인</a>` : ""}
                  </div>
                </div>
              </section>
            `;
          }).join("")}
        </div>
      ` : `<p class="planner-empty">URL과 날짜가 함께 검증된 확정 일정 후보가 아직 없습니다.</p>`}
    </article>
  `;
}

function renderTodoDraft(todos = []) {
  return `
    <article class="planner-todos">
      <h6>Todo List</h6>
      ${todos.length ? todos.map((item) => `
        <section class="planner-card">
          <strong>${escapeHtml(item.title || "Todo")}</strong>
          <p>${escapeHtml(item.related_gap || item.evidence || "")}</p>
          ${renderList(item.action_steps || [])}
          <small>${escapeHtml([item.priority, item.estimated_effort, item.due_basis].filter(Boolean).join(" · "))}</small>
          ${item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer">근거 확인</a>` : ""}
        </section>
      `).join("") : `<p class="planner-empty">Todo가 아직 없습니다.</p>`}
    </article>
  `;
}

function renderWorkflowStep(number, title, description, content, { current = false } = {}) {
  return `
    <section class="workflow-step ${current ? "is-current" : ""}">
      <header class="workflow-step-header">
        <span>STEP ${String(number).padStart(2, "0")}</span>
        <div>
          <h4>${escapeHtml(title)}</h4>
          ${description ? `<p>${escapeHtml(description)}</p>` : ""}
        </div>
      </header>
      <div class="workflow-step-body">${content}</div>
    </section>
  `;
}

function renderPlannerSection(planner = {}) {
  const calendar = planner.calendar_draft || [];
  const todos = planner.todo_list || [];
  const weekly = planner.weekly_plan || [];
  const uncertain = planner.uncertain_items || [];
  const sourceLinks = planner.source_links || [];

  return `
    <div class="planner-section">
      <div class="agent-header">
        <span class="result-label">실행 계획</span>
        <h5>Preparation Todo</h5>
        ${planner.planner_summary ? `<p>${escapeHtml(planner.planner_summary)}</p>` : ""}
      </div>

      <div class="planner-grid planner-stack">
        ${renderTodoDraft(todos)}
      </div>

      ${weekly.length ? `
        <div class="planner-weekly">
          <h6>Weekly Plan</h6>
          ${weekly.map((item) => `
            <article>
              <strong>${escapeHtml(item.week || "Week")}: ${escapeHtml(item.goal || "")}</strong>
              ${renderList(item.tasks || [])}
              <small>${escapeHtml(item.expected_output || "")}</small>
            </article>
          `).join("")}
        </div>
      ` : ""}

      ${uncertain.length ? `
        <div class="planner-uncertain">
          <h6>확인 필요 항목</h6>
          ${uncertain.map((item) => `
            <article>
              <strong>${escapeHtml(item.item || "확인 필요")}</strong>
              <p>${escapeHtml(item.reason || "")}</p>
              <small>${escapeHtml(item.needed_confirmation || "")}</small>
              ${item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer">출처 확인</a>` : ""}
            </article>
          `).join("")}
        </div>
      ` : ""}

      ${sourceLinks.length ? `
        <div class="planner-sources">
          <h6>Planner가 사용한 source</h6>
          ${sourceLinks.slice(0, 12).map((item) => `
            <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title || item.url)} <span>${escapeHtml(item.used_for || item.source_name || "")}</span></a>
          `).join("")}
        </div>
      ` : ""}
    </div>
  `;
}

function renderFeedbackLoop(loop) {
  if (!loop) return renderPlannerSection ? renderPlannerSection({}) : "";
  if (loop.error) {
    return `
      <div class="feedback-loop compact-result">
        <span class="result-label">Agent Review</span>
        <h4>Agent 검토를 실행하지 못했습니다.</h4>
        <p>${escapeHtml(loop.error)}</p>
        ${renderPlannerSection(loop.plannerResult || {})}
      </div>
    `;
  }

  const report = loop.leadingReport || {};
  const consult = loop.consultResult || {};
  const classification = consult.final_classification || {};
  const reviews = loop.supportingReviews || {};
  const reviewEntries = Object.entries(reviews);
  const recommendations = consult.recommendations || [];
  const activatedAgents = loop.activatedAgents || [];
  const conversations = loop.conversationLog || [];
  const planner = loop.plannerResult || {};
  const priorityGaps = consult.priority_gaps || report.critical_gaps || [];
  const focusItems = consult.recommended_focus || report.recommended_strategy || [];
  const nextActions = report.next_actions || [];

  const slides = [
    `
      <span class="slide-kicker">최종 판단</span>
      <h5>${escapeHtml(report.overall_status || classification.status || "분석 결과")}</h5>
      ${report.summary ? `<p>${escapeHtml(report.summary)}</p>` : ""}
      <div class="slide-two-col">
        <div><strong>우선 보완</strong>${renderCompactList(priorityGaps, 3)}</div>
        <div><strong>추천 방향</strong>${renderCompactList(focusItems, 3)}</div>
      </div>
    `,
    `
      <span class="slide-kicker">호출된 전문가</span>
      <h5>${activatedAgents.length ? `${activatedAgents.length}개 영역을 추가 검토했습니다.` : "추가 전문가 호출이 필요하지 않습니다."}</h5>
      <div class="mini-card-list">
        ${activatedAgents.length ? activatedAgents.map((item) => `<article><strong>${escapeHtml(item.agent_name || "Expert Agent")}</strong><p>${escapeHtml(item.reason || "보완 가능성을 확인했습니다.")}</p></article>`).join("") : "<p>현재 입력만으로 큰 보완 영역이 확인되지 않았습니다.</p>"}
      </div>
    `,
    reviewEntries.length ? `
      <span class="slide-kicker">전문가 검토 요약</span>
      <h5>영역별로 부족한 준비를 압축했습니다.</h5>
      <div class="mini-card-list">
        ${reviewEntries.map(([key, review]) => `
          <article>
            <strong>${escapeHtml(review.agent_name || key)}</strong>
            <p>${escapeHtml(plainText((review.assessment?.missing_or_weak_requirements || [])[0]) || "큰 약점은 확인되지 않았습니다.")}</p>
            ${renderCompactList((review.recommendations || []).map((item) => item.recommended_action || item.gap), 2)}
          </article>
        `).join("")}
      </div>
    ` : "",
    nextActions.length ? `
      <span class="slide-kicker">다음 행동</span>
      <h5>지금 바로 할 일을 우선순위로 정리했습니다.</h5>
      ${renderCompactList(nextActions, 5)}
    ` : "",
    recommendations.length ? `
      <span class="slide-kicker">추천 후보</span>
      <h5>보완에 도움이 되는 후보입니다.</h5>
      <div class="mini-card-list">
        ${recommendations.slice(0, 6).map((item) => `
          <article>
            <strong>${escapeHtml(item.title || "추천 후보")}</strong>
            <p>${escapeHtml(item.why_recommended || item.expected_cv_value || "지원 준비에 참고할 수 있습니다.")}</p>
            <small>${escapeHtml(item.source || item.type || "")}${item.deadline ? " · " + escapeHtml(item.deadline) : ""}</small>
            ${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">출처 보기</a>` : ""}
          </article>
        `).join("")}
      </div>
    ` : "",
    planner && Object.keys(planner).length ? `
      <span class="slide-kicker">Calendar & Todo</span>
      <h5>실행 계획 초안</h5>

    ` : "",
  ];

  const historyHtml = conversations.length ? `
    <details class="agent-history">
      <summary>
        <span>Agent 실행 기록 보기</span>
        <small>${conversations.length}개 메시지</small>
      </summary>
      <div class="history-list">
        ${conversations.map((item, index) => `
          <article>
            <span>${String(index + 1).padStart(2, "0")}</span>
            <div>
              <strong>${escapeHtml(item.from || "Agent")} → ${escapeHtml(item.to || "Agent")}</strong>
              <p>${escapeHtml(item.message || "")}</p>
            </div>
          </article>
        `).join("")}
      </div>
    </details>
  ` : "";

  return `
    <div class="feedback-loop compact-result">
      <div class="agent-header compact-header">
        <span class="result-label">Agent Review</span>
        <h4>${escapeHtml(report.overall_status || classification.status || "지원 전략 요약")}</h4>
        ${report.summary ? `<p>${escapeHtml(report.summary)}</p>` : ""}
      </div>
      <div class="feedback-status compact-status">
        <article><span>검토 영역</span><strong>${activatedAgents.length || 0}</strong></article>
        <article><span>보완 항목</span><strong>${priorityGaps.length || 0}</strong></article>
        <article><span>추천 행동</span><strong>${nextActions.length || recommendations.length || 0}</strong></article>
      </div>
      ${renderSlideDeck("Agent 상세 리포트", slides)}
      ${historyHtml}
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

function renderStreamingShell() {
  liveLaneState = {};
  resultCard.innerHTML = `
    <div class="live-agent-shell">
      <span class="result-label">실시간 Agent Feedback Loop</span>
      <h3>Agent들이 대화하며 보완 방향을 만들고 있습니다.</h3>
      <p class="extract-meta" id="liveStatus">입력한 Metadata를 서버로 보내고 있습니다.</p>
      <div class="analysis-loading"><span></span><span></span><span></span></div>

      <section class="live-chat-panel">
        <div class="agent-header">
          <span class="result-label">Agent Chat</span>
          <h4>실시간 대화</h4>
        </div>
        <div class="live-chat-stream" id="liveGlobalChat"></div>
      </section>

      <section class="lane-conversations live-lanes">
        <div class="agent-header">
          <span class="result-label">Expert Lanes</span>
          <h4>전문 Agent별 1:1 검토</h4>
        </div>
        <div class="lane-grid" id="liveLaneGrid"></div>
      </section>
    </div>
  `;
}

function ensureLiveLaneCard(meta = {}) {
  const key = meta.agentKey || meta.lane || meta.agent_key;
  const grid = document.querySelector("#liveLaneGrid");
  if (!grid || !key) return null;
  if (!liveLaneState[key]) {
    liveLaneState[key] = {
      agentName: meta.agentName || meta.agent_name || key,
      consultCloneName: meta.consultCloneName || `Leading Agent Review · ${meta.agentName || key}`,
      count: 0,
    };
    const lane = document.createElement("section");
    lane.className = "agent-lane";
    lane.dataset.lane = key;
    lane.innerHTML = `
      <div class="lane-heading">
        <span>${escapeHtml(key)}</span>
        <strong>${escapeHtml(liveLaneState[key].agentName)}</strong>
        <small>${escapeHtml(liveLaneState[key].consultCloneName)}</small>
      </div>
      <div class="lane-chat" data-lane-chat="${escapeHtml(key)}"></div>
    `;
    grid.appendChild(lane);
  }
  return [...grid.querySelectorAll("[data-lane-chat]")].find((item) => item.dataset.laneChat === key) || null;
}

function createLiveBubble(message, index) {
  const row = document.createElement("article");
  row.className = `dialogue-turn ${getConversationToneClass(message?.from)}`;
  row.innerHTML = `
    <span>${String(index).padStart(2, "0")}</span>
    <div>
      <strong>${escapeHtml(message?.from || "Agent")} → ${escapeHtml(message?.to || "System")}</strong>
      <p>${escapeHtml(message?.message || "")}</p>
    </div>
  `;
  return row;
}

function appendLiveConversation(message) {
  if (!message?.message) return;
  const globalChat = document.querySelector("#liveGlobalChat");
  if (globalChat) {
    const globalIndex = globalChat.querySelectorAll(".dialogue-turn").length + 1;
    const globalRow = createLiveBubble(message, globalIndex);
    globalChat.appendChild(globalRow);
    globalRow.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  const laneKey = message?.lane || message?.agent_key;
  if (!laneKey) return;
  const container = ensureLiveLaneCard({ agentKey: laneKey, agentName: message.agentName || message.to });
  if (!container) return;
  const laneIndex = container.querySelectorAll(".dialogue-turn").length + 1;
  const row = createLiveBubble(message, laneIndex);
  container.appendChild(row);
  row.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function setLiveStatus(message) {
  const status = document.querySelector("#liveStatus");
  if (status && message) status.textContent = message;
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

function buildAnalyzePayload() {
  const metadata = getMetadata();
  const preferences = getPreferences();
  return {
    target_role: preferences.target_role,
    cv_text: `${getManualText()}\n\n사용자 선호: ${JSON.stringify(preferences, null, 2)}\n\nMetadata: ${JSON.stringify(metadata, null, 2)}`,
    metadata,
    preferences,
  };
}

async function analyzeManualStream() {
  const response = await fetch("/api/analyze-cv-stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildAnalyzePayload()),
  });

  if (!response.ok || !response.body) {
    throw new Error("실시간 분석 API가 연결되지 않았습니다.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalData = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      let item;
      try {
        item = JSON.parse(line);
      } catch {
        setLiveStatus("실시간 메시지 일부가 깨져 건너뛰고 있습니다. 분석은 계속 진행 중입니다.");
        continue;
      }
      if (item.event === "status") {
        setLiveStatus(item.payload?.message || "");
      }
      if (item.event === "conversation") {
        appendLiveConversation(item.payload);
      }
      if (item.event === "agents_selected") {
        setLiveStatus(`Leading Agent가 ${(item.payload?.activatedAgents || []).length}개의 Supporting Agent를 선택했습니다.`);
      }
      if (item.event === "lane_started") {
        ensureLiveLaneCard(item.payload || {});
        setLiveStatus(`${item.payload?.agentName || "Supporting Agent"} lane이 시작되었습니다.`);
      }
      if (item.event === "supporting_review") {
        setLiveStatus(`${item.payload?.review?.agent_name || "Supporting Agent"}의 검토 결과가 도착했습니다.`);
      }
      if (item.event === "consult_clone_review") {
        setLiveStatus(`${item.payload?.lane?.agent_name || "Support Agent"} 검토가 완료되었습니다.`);
      }
      if (item.event === "consult_result") {
        setLiveStatus("Leading Agent가 Supporting Agent 결과를 통합했습니다.");
      }
      if (item.event === "planner_result") {
        setLiveStatus("실행 계획 초안을 정리했습니다.");
      }
      if (item.event === "final") {
        finalData = item.payload;
      }
      if (item.event === "error") {
        throw new Error(item.payload?.message || "실시간 분석 중 오류가 발생했습니다.");
      }
    }
  }

  if (!finalData) {
    throw new Error("실시간 분석 결과를 받지 못했습니다.");
  }
  return finalData;
}

async function renderReport() {
  const preferences = getPreferences();
  if (!preferences.target_role) {
    renderMessage("목표 직무 필요", "지원 목표를 먼저 입력해주세요.", ["예: AI Research Engineer, 데이터 분석 인턴, 프론트엔드 신입"]);
    document.querySelector("#preferenceRole")?.focus();
    return;
  }

  const cvText = getManualText();
  if (!cvText.trim()) {
    renderMessage("이력서 내용 필요", "분석할 이력서 내용이 비어 있어요.", ["PDF를 업로드하거나 직접 입력으로 경험을 작성해주세요."]);
    return;
  }

  analyzeButton.disabled = true;
  analyzeButton.textContent = "진단 중입니다...";
  renderStreamingShell();

  try {
    const data = await analyzeManualStream();
    renderAnalysis(data);
  } catch (error) {
    renderMessage("분석 실패", error.message || "분석 중 문제가 발생했습니다.", ["반드시 `http://localhost:4173/diagnosis.html`에서 열어주세요.", "서버 실행: `cd /root/hicareer && PORT=4173 python3 server.py`"]);
  } finally {
    analyzeButton.disabled = false;
    analyzeButton.textContent = "내 이력서 진단하기";
  }
}


async function extractPdfToForm() {
  const file = cvFile.files[0];
  if (!file) {
    renderMessage("PDF 대기 중", "이력서 PDF를 먼저 선택해주세요.", ["파일을 선택하면 자동으로 내용을 정리합니다."]);
    return;
  }

  renderMessage("PDF 정리 중", "이력서 내용을 읽고 항목별로 정리하고 있어요.", ["잠시만 기다려주세요. 완료되면 아래 입력칸에 자동으로 채워집니다.", "정리된 내용은 분석 전에 직접 수정할 수 있습니다."]);

  const formData = new FormData();
  formData.append("cv_file", file);
  formData.append("target_role", "");

  try {
    const response = await fetch("/api/extract-cv", { method: "POST", body: formData });
    const data = await readJsonResponse(response);
    if (data.fields) seedMetadataFromFields(data.fields);
    if (data.metadata) {
      metadataState = Object.fromEntries(Object.keys(metadataConfig).map((key) => [key, Array.isArray(data.metadata[key]) ? data.metadata[key] : []]));
    }
    setInputMode("manual");
    renderMetadataEditor();
    analyzeButton.classList.remove("hidden");
    renderMessage("PDF 정리 완료", "이력서 내용을 입력칸에 채웠습니다.", ["빠진 경험이나 어색한 표현을 수정한 뒤 진단을 실행하세요."]);
  } catch (error) {
    renderMessage("PDF 정리 실패", error.message || "PDF 내용을 정리하지 못했습니다.", ["서버를 `python3 server.py`로 실행했는지 확인해주세요.", "OPENAI_API_KEY가 설정되어 있어야 PDF 정리가 가능합니다."]);
  }
}

function renderAnalysis(data) {
  const summary = data.summary || {};
  const rankedJobs = data.feedbackLoop?.recommendedJobs || data.rankedJobs || [];
  const topJob = rankedJobs[0];
  const llmReport = data.llmReport || {};
  const quickStrengths = getQuickStrengths(data);
  const quickGaps = getQuickGaps(data);
  const quickActions = getQuickActions(data);
  const activatedCount = data.feedbackLoop?.activatedAgents?.length || 0;
  const jobSlides = rankedJobs.slice(0, 10).map((job, index) => {
    const note = getJobNoteFor(job, llmReport);
    const reasonItems = note?.fitReason ? [note.fitReason] : (job.recommendationReason ? [job.recommendationReason] : (job.fitReasons || []));
    const riskItems = note?.risk ? [note.risk] : (job.gaps || []);
    return `
      <span class="slide-kicker">추천 공고 ${index + 1}</span>
      <div class="job-slide-top">
        <h5>${escapeHtml(job.title)}</h5>
        <span class="fit high">Fit ${job.fit}</span>
      </div>
      <p class="company">${escapeHtml(job.company || "")}</p>
      <p class="job-meta">${escapeHtml(job.location || "")}${job.deadline ? " · " + escapeHtml(job.deadline) : ""}</p>
      <div class="skill-row">${(job.skills || []).slice(0, 5).map((skill) => `<span>${escapeHtml(skill)}</span>`).join("")}</div>
      <div class="slide-two-col">
        <div><strong>왜 추천하나요</strong>${renderFullList(reasonItems)}</div>
        <div><strong>지원 전 보완할 점</strong>${renderFullList(riskItems)}</div>
      </div>
      ${job.url ? `<a class="slide-link" href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer">공고 보기</a>` : ""}
    `;
  });

  resultCard.innerHTML = `
    <div class="result-hero-summary">
      <span class="result-label">진단 결과</span>
      <h3>${escapeHtml(summary.targetRole || "목표 직무")} 기준으로 지원 전략을 정리했습니다.</h3>
      <p>${escapeHtml(llmReport.headline || (topJob ? `가장 적합한 후보는 ${topJob.title}이며, 총 ${rankedJobs.length}개 공고를 비교했습니다.` : "이력서 내용을 바탕으로 강점과 보완 방향을 정리했습니다."))}</p>
      <div class="summary-grid compact-summary">
        <div><strong>${rankedJobs.length}</strong><span>비교 공고</span></div>
        <div><strong>${topJob?.fit || "-"}</strong><span>최고 Fit</span></div>
        <div><strong>${activatedCount}</strong><span>검토 Agent</span></div>
      </div>
    </div>

    <div class="quick-insights">
      <article>
        <span>강점</span>
        <h4>앞에 배치할 내용</h4>
        ${renderCompactList(quickStrengths, 3)}
      </article>
      <article>
        <span>보완</span>
        <h4>더 준비하면 좋은 내용</h4>
        ${renderCompactList(quickGaps, 3)}
      </article>
    </div>

    ${quickActions.length ? `
      <div class="quick-action-card">
        <span>다음 행동</span>
        <h4>우선순위가 높은 실행 계획</h4>
        ${renderFullList(quickActions)}
      </div>
    ` : ""}

    ${renderFeedbackLoop(data.feedbackLoop)}
    ${jobSlides.length ? renderSlideDeck("추천 채용공고", jobSlides) : ""}
  `;
  bindActionChecks();
  bindSlideDecks();
}


hasPdfButton.addEventListener("click", () => setInputMode("pdf"));
noPdfButton.addEventListener("click", () => setInputMode("manual"));
backFromPdf?.addEventListener("click", resetInputMode);
backFromManual?.addEventListener("click", resetInputMode);
cvFile.addEventListener("change", () => {
  fileName.textContent = cvFile.files[0]?.name || "이력서 또는 CV 파일을 올려주세요.";
  if (cvFile.files[0]) extractPdfToForm();
});
analyzeButton.addEventListener("click", renderReport);
document.querySelector("#metadataSections")?.addEventListener("click", (event) => {
  const addButton = event.target.closest(".add-metadata");
  const removeButton = event.target.closest(".remove-metadata");
  if (addButton) {
    getMetadata();
    const category = addButton.dataset.category;
    metadataState[category].push(createEmptyMetadataItem(category));
    renderMetadataEditor();
  }
  if (removeButton) {
    getMetadata();
    const item = removeButton.closest(".metadata-item");
    metadataState[item.dataset.category].splice(Number(item.dataset.index), 1);
    renderMetadataEditor();
  }
});
renderMetadataEditor();
