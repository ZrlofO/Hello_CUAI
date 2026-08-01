const workflowForm = document.querySelector("#workflowForm");
const cvFile = document.querySelector("#cvFile");
const fileName = document.querySelector("#fileName");
const extractButton = document.querySelector("#extractButton");
const statusCard = document.querySelector("#statusCard");
const statusTitle = document.querySelector("#statusTitle");
const statusText = document.querySelector("#statusText");
const reviewSection = document.querySelector("#reviewSection");
const metadataPreferences = document.querySelector("#metadataPreferences");
const metadataGroups = document.querySelector("#metadataGroups");
const revisionLabel = document.querySelector("#revisionLabel");
const addItemForm = document.querySelector("#addItemForm");
const newCategory = document.querySelector("#newCategory");
const newValue = document.querySelector("#newValue");
const confirmButton = document.querySelector("#confirmButton");
const discussionPanel = document.querySelector("#discussionPanel");

let workflow = null;
let discussionPollTimer = null;

function workflowPathId() {
  return workflow && (workflow.workflow_id || workflow.request_id);
}

const categoryLabels = {
  activities_and_career_experience: "Activities and career experience",
  awards: "Awards",
  leadership_and_contribution: "Leadership and contribution",
  volunteering_and_contribution: "Volunteering and contribution",
  language_proficiency: "Language proficiency",
  certifications_and_credentials: "Certifications and credentials",
  projects: "Projects",
  research: "Research",
  internships: "Internships",
  competitions: "Competitions",
  technical_skills: "Technical skills",
  education_and_training: "Education and training",
  additional_information: "Additional information",
};

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setStatus(title, message, isError) {
  statusTitle.textContent = title;
  statusText.textContent = message;
  statusCard.classList.toggle("caution-card", Boolean(isError));
}

async function readJson(response) {
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "요청에 실패했습니다.");
    error.payload = data;
    throw error;
  }
  return data;
}

function renderPreferences() {
  const preferences = workflow.normalized_metadata.preferences;
  metadataPreferences.innerHTML =
    '<span class="result-label">Preference information</span>' +
    "<h3>" + escapeHtml(preferences.preferred_role || "목표 직무 미입력") + "</h3>" +
    "<p>준비 기간: " + escapeHtml(preferences.preparation_period || "미입력") + "</p>" +
    (preferences.additional_information ? "<p>추가 정보: " + escapeHtml(preferences.additional_information) + "</p>" : "") +
    "<small class=\"extract-meta\">normalization: " + escapeHtml(workflow.normalized_metadata.normalization_method || "-") + "</small>" +
    '<small class="extract-meta">PDF ' + escapeHtml(workflow.pdf.filename) + " · " + workflow.pdf.page_count + " pages · " + escapeHtml(workflow.pdf.extraction_method) + "</small>";
}

function renderGroups() {
  const groups = new Map();
  workflow.normalized_metadata.items.forEach(function(item) {
    if (!groups.has(item.category)) groups.set(item.category, []);
    groups.get(item.category).push(item);
  });

  if (!workflow.normalized_metadata.items.length) {
    metadataGroups.innerHTML = '<article class="wide-card caution-card"><h3>추출된 항목이 없습니다.</h3><p>이미지 기반 PDF일 수 있습니다. 아래 추가 정보 입력을 사용해 보완하세요.</p></article>';
    return;
  }

  metadataGroups.innerHTML = Array.from(groups.entries()).map(function(entry) {
    const category = entry[0];
    const items = entry[1];
    return '<article class="wide-card">' +
      '<span class="eyebrow">' + escapeHtml(categoryLabels[category] || category) + "</span>" +
      '<div class="metadata-items">' +
      items.map(function(item) {
        return '<div class="metadata-item" data-item-id="' + escapeHtml(item.item_id) + '">' +
          '<div class="metadata-item-main">' +
          '<textarea class="metadata-value">' + escapeHtml(item.normalized_value) + "</textarea>" +
          (item.keywords && item.keywords.length ? '<small class="metadata-keywords">keywords: ' + escapeHtml(item.keywords.join(", ")) + '</small>' : '') +
          "<small>provenance: " + escapeHtml(item.provenance) +
          " · confidence: " + Number(item.extraction_confidence).toFixed(2) +
          (item.source_page ? " · page " + item.source_page : "") + "</small></div>" +
          '<div class="metadata-item-actions"><button type="button" class="button secondary save-item">수정</button>' +
          '<button type="button" class="button secondary delete-item">삭제</button></div></div>';
      }).join("") + "</div></article>";
  }).join("");

  document.querySelectorAll(".save-item").forEach(function(button) {
    button.addEventListener("click", function() { updateItem(button.closest(".metadata-item")); });
  });
  document.querySelectorAll(".delete-item").forEach(function(button) {
    button.addEventListener("click", function() { deleteItem(button.closest(".metadata-item")); });
  });
}

function renderReview() {
  revisionLabel.textContent = "revision " + workflow.revision;
  renderPreferences();
  renderGroups();
  reviewSection.classList.remove("hidden");
}

function renderDiscussion(discussion) {
  if (!discussionPanel || !discussion) return;
  discussionPanel.innerHTML =
    '<div class="agent-header"><span class="result-label">Agent Communication</span>' +
    '<h4>Agent Communication</h4><p>' + escapeHtml((discussion.warnings || []).join(" ")) + "</p>" +
    '<small class="extract-meta">last update: ' + escapeHtml(discussion.updated_at || "-") + '</small></div>' +
    '<div class="discussion-flow">' +
    (discussion.discussionHistory || []).map(function(turn, index) {
      return '<article class="dialogue-turn ' + escapeHtml(turn.tone || "agent") + '">' +
        '<span>' + String(index + 1).padStart(2, "0") + '</span><div>' +
        '<strong>' + escapeHtml(turn.speaker) + '</strong>' +
        '<p>' + escapeHtml(turn.message) + '</p>' +
        '<small>status: ' + escapeHtml(turn.status) +
        (turn.evidence_refs && turn.evidence_refs.length ? ' · evidence refs: ' + turn.evidence_refs.length : '') +
        '</small></div></article>';
    }).join("") + '</div>';
  discussionPanel.classList.remove("hidden");
}

function stopDiscussionPolling() {
  if (discussionPollTimer) {
    clearTimeout(discussionPollTimer);
    discussionPollTimer = null;
  }
}

async function pollDiscussion() {
  if (!workflow || !workflowPathId()) return;
  try {
    const response = await fetch("/api/workflows/" + workflowPathId() + "/discussion", {
      headers: { "Accept": "application/json" },
      cache: "no-store",
    });
    const discussion = await readJson(response);
    renderDiscussion(discussion);
    discussionPollTimer = setTimeout(pollDiscussion, Number(discussion.next_poll_ms || 1500));
  } catch (error) {
    discussionPollTimer = setTimeout(pollDiscussion, 3000);
  }
}

function startDiscussionPolling() {
  stopDiscussionPolling();
  pollDiscussion();
}

async function createWorkflow(event) {
  event.preventDefault();
  if (!cvFile.files.length) {
    setStatus("PDF가 필요합니다.", "PDF 파일을 선택해 주세요.", true);
    return;
  }
  const formData = new FormData(workflowForm);
  extractButton.disabled = true;
  setStatus("metadata 추출 중", "PDF를 검증하고 텍스트와 source reference를 추출하고 있습니다.", false);
  try {
    const response = await fetch("/api/workflows", { method: "POST", body: formData });
    workflow = await readJson(response);
    setStatus("검토 필요", "추출 결과를 확인하고 수정한 뒤 확정하세요.", false);
    renderReview();
  } catch (error) {
    setStatus("추출 실패", error.message, true);
  } finally {
    extractButton.disabled = false;
  }
}

async function updateItem(element) {
  const value = element.querySelector(".metadata-value").value.trim();
  if (!value) {
    setStatus("수정할 수 없습니다.", "metadata 내용은 비워둘 수 없습니다.", true);
    return;
  }
  try {
    const response = await fetch("/api/workflows/" + workflowPathId() + "/metadata/items/" + element.dataset.itemId, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base_revision: workflow.revision, normalized_value: value }),
    });
    workflow = await readJson(response);
    setStatus("수정 완료", "사용자 수정 내용이 저장되었습니다.", false);
    renderReview();
  } catch (error) {
    setStatus("수정 실패", error.message, true);
  }
}

async function deleteItem(element) {
  if (!window.confirm("이 metadata 항목을 삭제할까요?")) return;
  try {
    const response = await fetch("/api/workflows/" + workflowPathId() + "/metadata/items/" + element.dataset.itemId, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base_revision: workflow.revision }),
    });
    workflow = await readJson(response);
    setStatus("삭제 완료", "항목이 삭제되었습니다.", false);
    renderReview();
  } catch (error) {
    setStatus("삭제 실패", error.message, true);
  }
}

async function addMetadataItem(event) {
  event.preventDefault();
  const value = newValue.value.trim();
  if (!value) return;
  try {
    const response = await fetch("/api/workflows/" + workflowPathId() + "/metadata/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        base_revision: workflow.revision,
        category: newCategory.value,
        normalized_value: value,
        original_text: value,
      }),
    });
    workflow = await readJson(response);
    newValue.value = "";
    setStatus("추가 완료", "사용자 제공 metadata가 추가되었습니다.", false);
    renderReview();
  } catch (error) {
    setStatus("추가 실패", error.message, true);
  }
}

async function confirmMetadata() {
  confirmButton.disabled = true;
  try {
    const response = await fetch("/api/workflows/" + workflowPathId() + "/metadata/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base_revision: workflow.revision }),
    });
    workflow = await readJson(response);
    localStorage.setItem("hicareer.workflow_id", workflowPathId());
    setStatus("metadata 확정 완료", "확정된 프로필이 저장되었습니다. 현재 리포트를 확인합니다.", false);
    confirmButton.textContent = "확정 완료";
    startDiscussionPolling();
    window.location.href = "report.html?workflow_id=" + encodeURIComponent(workflowPathId());
  } catch (error) {
    setStatus("확정 실패", error.message, true);
    confirmButton.disabled = false;
  }
}

cvFile.addEventListener("change", function() {
  fileName.textContent = cvFile.files[0] ? cvFile.files[0].name : "CV PDF를 선택하세요";
});
workflowForm.addEventListener("submit", createWorkflow);
addItemForm.addEventListener("submit", addMetadataItem);
confirmButton.addEventListener("click", confirmMetadata);
