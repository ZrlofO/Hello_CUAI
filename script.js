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
  return { target_role: document.querySelector("#preferenceRole")?.value.trim() || pdfRoleInput.value.trim(), preparation_period: document.querySelector("#preferencePeriod")?.value.trim() || "", additional_user_input: document.querySelector("#preferenceAdditional")?.value.trim() || "" };
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
        <div><span>Planner Agent</span><h6>Calendar Draft</h6></div>
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
        <span class="result-label">Planner Agent</span>
        <h5>Calendar Draft & Todo</h5>
        ${planner.planner_summary ? `<p>${escapeHtml(planner.planner_summary)}</p>` : ""}
      </div>

      <div class="planner-grid planner-stack">
        ${renderCalendarDraft(calendar)}
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
  if (!loop) return renderWorkflowStep(5, "Calendar & Todo", "다음 행동을 계획하는 단계입니다.", renderPlannerSection({}), { current: true });
  if (loop.error) {
    return `
      ${renderWorkflowStep(2, "Agent Feedback Loop", "분석 과정에서 일부 오류가 발생했습니다.", `<p>${escapeHtml(loop.error)}</p>`)}
      ${renderWorkflowStep(5, "Calendar & Todo", "일정과 할 일을 확인하고 등록할 수 있습니다.", renderPlannerSection(loop.plannerResult || {}), { current: true })}
    `;
  }

  const report = loop.leadingReport || {};
  const consult = loop.consultResult || {};
  const classification = consult.final_classification || {};
  const reviews = loop.supportingReviews || {};
  const reviewEntries = Object.entries(reviews);
  const recommendations = consult.recommendations || [];
  const planner = loop.plannerResult || {};

  return `
    ${renderWorkflowStep(2, "Agent 대화 및 호출 판단", report.summary || "Leading Agent와 Consult Agent가 검토 범위를 정했습니다.", `
      <div class="feedback-status">
        <article>
          <span>최종 상태</span>
          <strong>${report.overall_status || classification.status || "분류 대기"}</strong>
        </article>
        <article>
          <span>실행 방식</span>
          <strong>${loop.mode || "multi_call"}</strong>
        </article>
        <article>
          <span>활성화 Agent</span>
          <strong>${(loop.activatedAgents || []).length}</strong>
        </article>
      </div>

      <div class="conversation-log discussion-flow">
        <div class="agent-header">
          <span class="result-label">Agent Conversation</span>
          <h4>Global Agent Timeline</h4>
        </div>
        <div class="discussion-flow-list">
          ${(loop.conversationLog || []).filter((item) => !item.lane && !item.agent_key).map(renderAgentConversationItem).join("")}
        </div>
      </div>

      <div class="activated-agents">
        <h5>Consult Agent의 호출 판단</h5>
        ${(loop.activatedAgents || []).map((item) => `
          <article>
            <strong>${item.agent_name}</strong>
            <p>${item.reason}</p>
          </article>
        `).join("")}
      </div>
    `)}

    ${renderWorkflowStep(3, "Supporting Agent 병렬 검토", "각 전문 Agent가 보완할 증거와 실행 방향을 검토했습니다.", `
      <div class="supporting-reviews">
        <h5>Supporting Agent 검토 결과</h5>
        ${reviewEntries.map(([key, review]) => `
          <article>
            <span>${key}</span>
            <h6>${review.agent_name || key}</h6>
            <div class="review-grid">
              <div>
                <strong>충족된 기준</strong>
                ${renderList(review.assessment?.fulfilled_requirements || [])}
              </div>
              <div>
                <strong>부족하거나 약한 기준</strong>
                ${renderList(review.assessment?.missing_or_weak_requirements || [])}
              </div>
              <div>
                <strong>불명확한 지점</strong>
                ${renderList(review.assessment?.unclear_points || [])}
              </div>
            </div>
            <div class="recommendation-list">
              ${(review.recommendations || []).map((item) => `
                <section>
                  <strong>${item.gap || "보완 항목"}</strong>
                  <p>${item.recommended_action || ""}</p>
                  <small>${item.reason || ""}${item.time_fit ? ` · ${item.time_fit}` : ""}</small>
                </section>
              `).join("")}
            </div>
          </article>
        `).join("")}
      </div>
    `)}

    ${renderWorkflowStep(4, "Consult Agent 최종 통합", "검토 결과와 외부 검색 근거를 바탕으로 우선순위를 정했습니다.", `
      <div class="consult-final">
        <h5>Consult Agent 최종 통합</h5>
        ${renderList(classification.reason || [])}
        <div class="review-grid">
          <div><strong>우선 보완 Gap</strong>${renderList(consult.priority_gaps || report.critical_gaps || [])}</div>
          <div><strong>추천 Focus</strong>${renderList(consult.recommended_focus || report.recommended_strategy || [])}</div>
          <div><strong>다음 Action</strong>${renderList(report.next_actions || [])}</div>
        </div>
      </div>

      ${recommendations.length ? `
        <div class="retrieval-recommendations">
          <h5>Retrieval 기반 추천 후보</h5>
          ${recommendations.map((item) => `
            <article>
              <strong>${item.title || "추천 후보"}</strong>
              <p>${item.why_recommended || item.expected_cv_value || ""}</p>
              <small>${item.source || item.type || ""}${item.deadline ? ` · ${item.deadline}` : ""}${item.status_note ? ` · ${item.status_note}` : ""}</small>
              ${item.url ? `<a href="${item.url}" target="_blank" rel="noopener noreferrer">출처 확인</a>` : ""}
            </article>
          `).join("")}
        </div>
      ` : ""}
    `)}

    ${renderWorkflowStep(5, "Calendar & Todo", "확정된 우선순위를 일정과 실행 항목으로 옮겼습니다.", renderPlannerSection(planner), { current: true })}
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
    <span class="result-label">실시간 Agent Feedback Loop</span>
    <h3>Agent들이 대화하며 보완 방향을 만들고 있습니다.</h3>
    <p class="extract-meta" id="liveStatus">입력한 Metadata를 서버로 보내고 있습니다.</p>
    <div class="analysis-loading"><span></span><span></span><span></span></div>
    <div class="lane-conversations live-lanes">
      <div class="agent-header">
        <span class="result-label">Parallel Agent Lanes</span>
        <h4>Consult Clone ↔ Supporting Agent 1:1 대화</h4>
      </div>
      <div class="lane-grid" id="liveLaneGrid"></div>
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
      consultCloneName: meta.consultCloneName || `Consult Agent Clone · ${meta.agentName || key}`,
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

function appendLiveConversation(message) {
  const laneKey = message?.lane || message?.agent_key;
  if (!laneKey) {
    if (message?.from && message?.to) {
      setLiveStatus(`${message.from} → ${message.to}: ${message.message}`);
    }
    return;
  }
  const container = ensureLiveLaneCard({ agentKey: laneKey });
  if (!container || !message?.message) return;
  const row = document.createElement("article");
  const turnNumber = container.querySelectorAll(".dialogue-turn").length + 1;
  row.className = `dialogue-turn ${getConversationToneClass(message.from)}`;
  row.innerHTML = `
    <span>${String(turnNumber).padStart(2, "0")}</span>
    <div>
      <strong>${escapeHtml(message.from)} → ${escapeHtml(message.to)}</strong>
      <p>${escapeHtml(message.message)}</p>
    </div>
  `;
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
        setLiveStatus(`Consult Agent가 ${(item.payload?.activatedAgents || []).length}개의 Supporting Agent를 선택했습니다.`);
      }
      if (item.event === "lane_started") {
        ensureLiveLaneCard(item.payload || {});
        setLiveStatus(`${item.payload?.agentName || "Supporting Agent"} lane이 시작되었습니다.`);
      }
      if (item.event === "supporting_review") {
        setLiveStatus(`${item.payload?.review?.agent_name || "Supporting Agent"}의 검토 결과가 도착했습니다.`);
      }
      if (item.event === "consult_clone_review") {
        setLiveStatus(`${item.payload?.lane?.agent_name || "Support Agent"} lane의 Consult Clone 검토가 완료되었습니다.`);
      }
      if (item.event === "consult_result") {
        setLiveStatus("Consult Agent가 최종 통합 결과를 전달했습니다.");
      }
      if (item.event === "planner_result") {
        setLiveStatus("Planner Agent가 Calendar Draft와 Todo 초안을 전달했습니다.");
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
    <section class="workflow-section" aria-label="분석 워크플로우">
      <div class="workflow-section-header">
        <div>
          <span class="result-label">Analysis Workflow</span>
          <h4>단계별 결과를 옆으로 넘겨 확인하세요.</h4>
        </div>
        <small>가로 스크롤</small>
      </div>
      <div class="workflow-steps">
        ${renderWorkflowStep(1, "CV 초기 진단", "입력한 Metadata와 목표 직무를 기준으로 현재 증거를 정리했습니다.", `
          ${renderLlmReport(data.llmReport)}
          <div class="analysis-block">
            <h4>강점</h4>
            <ul>${summary.strengths.map((item) => `<li>${item}</li>`).join("")}</ul>
          </div>
          <div class="analysis-block">
            <h4>보완할 증거</h4>
            <ul>${summary.gaps.map((item) => `<li>${item}</li>`).join("")}</ul>
          </div>
        `)}
        ${renderFeedbackLoop(data.feedbackLoop)}
        ${renderWorkflowStep(6, "Retrieval Fit 결과", "추천 채용공고와 초기 AI 분석을 다시 확인할 수 있습니다.", `
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
        `)}
      </div>
    </section>
  `;
  bindActionChecks();
}

function fillManualFields(fields) {
  document.querySelector("#preferenceRole").value = fields.targetRole || pdfRoleInput.value.trim();
  seedMetadataFromFields(fields);
}

async function extractPdfToForm() {
  if (cvFile.files.length === 0) {
    renderMessage("PDF 대기 중", "먼저 CV PDF를 업로드해주세요.", ["PDF를 선택하면 Agent가 Metadata 항목을 자동으로 채웁니다."]);
    return;
  }

  const formData = new FormData();
  formData.append("cv_file", cvFile.files[0]);
  formData.append("target_role", pdfRoleInput.value.trim());
  renderMessage("PDF 추출 중", "LLM이 PDF를 읽고 Metadata 항목으로 분류하고 있어요.", ["분류된 항목을 직접 수정한 다음 Agent 실행 버튼을 눌러주세요."]);
  extractButton.disabled = true;

  try {
    const response = await fetch("/api/extract-cv", { method: "POST", body: formData });
    const data = await readJsonResponse(response);
    fillManualFields(data.fields || {});
    setInputMode("manual");
    renderMessage("정리 완료", "LLM이 PDF를 읽고 Metadata 항목을 채웠습니다.", [
      "각 항목의 제목과 내용을 확인하고 필요한 부분을 수정한 뒤 Agent를 실행해주세요.",
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
    body: JSON.stringify(buildAnalyzePayload()),
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
    renderMessage("먼저 PDF 정리", "PDF를 바로 분석하지 않고 LLM이 Metadata를 먼저 정리합니다.", ["`LLM으로 PDF 정리해서 입력칸 채우기` 버튼을 누른 뒤 Metadata와 preference를 수정해주세요."]);
    return;
  }

  if (isManualMode && !getManualText() && !getPreferences().additional_user_input) {
    renderMessage("입력 필요", "Metadata 항목을 하나 이상 추가하거나 내용을 입력해주세요.", ["PDF가 없다면 Metadata의 '+ 항목 추가'로 직접 입력할 수 있습니다."]);
    return;
  }

  renderStreamingShell();
  analyzeButton.disabled = true;

  try {
    const data = await analyzeManualStream();
    renderAnalysis(data);
  } catch (error) {
    renderMessage("기본 결과로 전환", "실시간 Agent 대화를 끝까지 표시하지 못했습니다.", ["입력한 Metadata는 유지되어 있습니다. 잠시 후 Agent 실행을 다시 눌러주세요."]);
  } finally {
    analyzeButton.disabled = false;
  }
}

hasPdfButton.addEventListener("click", () => setInputMode("pdf"));
noPdfButton.addEventListener("click", () => setInputMode("manual"));
backFromPdf?.addEventListener("click", resetInputMode);
backFromManual?.addEventListener("click", resetInputMode);
cvFile.addEventListener("change", () => {
  fileName.textContent = cvFile.files[0]?.name || "이력서 또는 CV 파일을 올려주세요.";
  if (cvFile.files[0]) extractPdfToForm();
});
extractButton?.addEventListener("click", extractPdfToForm);
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
