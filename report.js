(function () {
  const status = document.querySelector("#reportStatus");
  const content = document.querySelector("#reportContent");
  function escapeHtml(value) {
    return String(value == null ? "" : value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }
  function list(items, emptyText) {
    if (!items || !items.length) return '<p class="empty-inline">' + escapeHtml(emptyText) + "</p>";
    return "<ul>" + items.map(function (item) {
      const value = typeof item === "string" ? item : (item.value || item.title || item.claim_text || item.requirement || JSON.stringify(item));
      return "<li>" + escapeHtml(value) + "</li>";
    }).join("") + "</ul>";
  }
  function card(label, title, body) {
    return '<article class="wide-card report-section"><span class="eyebrow">' + escapeHtml(label) + "</span><h3>" + escapeHtml(title) + "</h3>" + body + "</article>";
  }
  function render(report) {
    const summary = report.summary || {};
    const profile = report.profile_summary || {};
    const readiness = report.readiness_classification || {};
    const graph = report.graph_status || {};
    const citations = report.citations || [];
    status.innerHTML = '<span class="result-label">' + escapeHtml(report.status || "PARTIAL") + '</span><h3>' + escapeHtml(summary.preferred_role || "Target role not provided") + '</h3><p>준비 기간: ' + escapeHtml(summary.preparation_period || "미입력") + ' · workflow: ' + escapeHtml(report.workflow_id) + '</p>';
    content.innerHTML = '<section class="report-grid"><article class="metric-card"><span>Readiness</span><strong>' + escapeHtml(readiness.label || "미분류") + '</strong><p>' + escapeHtml(readiness.disclaimer || "고용 또는 합격을 보장하지 않는 보수적 추정입니다.") + '</p></article><article class="metric-card"><span>Evidence</span><strong>' + escapeHtml(summary.evidence_count || 0) + '</strong><p>claims ' + escapeHtml(summary.claim_count || 0) + ' · metadata items ' + escapeHtml(summary.metadata_item_count || 0) + '</p></article></section>' + card("Profile", "확정된 사용자 프로필", list(profile.items || [], "확정된 metadata가 없습니다.")) + card("Market analysis", "시장 분석", list((report.market_analysis || {}).requirements || [], "아직 승인된 시장 분석이 없습니다.")) + card("Strengths", "확인된 강점", list(report.strengths, "아직 승인된 강점 분석이 없습니다.")) + card("Gaps", "확인된 개선 영역", list(report.weaknesses, "아직 승인된 gap 분석이 없습니다.")) + card("Recommendations", "승인된 추천 및 계획", list(report.recommendations, "아직 승인된 추천이 없습니다.")) + card("Todo", "구조화된 할 일", list(report.todo_items, "아직 Planner 결과가 없습니다.")) + card("Citations", "근거 링크", citations.length ? "<ul>" + citations.map(function (item) { return '<li><a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(item.title || item.url) + '</a><small> evidence: ' + escapeHtml(item.evidence_id) + '</small></li>'; }).join("") + "</ul>" : '<p class="empty-inline">검증된 외부 근거가 없습니다.</p>') + card("Uncertainty", "주의사항", list(report.uncertainty_notes, "주의사항이 없습니다.")) + '<article class="result-card report-state"><span class="result-label">Graph status</span><p>' + escapeHtml(graph.status || "UNKNOWN") + ' · checkpointed: ' + escapeHtml(graph.checkpointed) + ' · interrupt: ' + escapeHtml(graph.interrupt_required) + '</p></article>';
    content.classList.remove("hidden");
  }
  async function load() {
    const workflowId = new URLSearchParams(window.location.search).get("workflow_id") || localStorage.getItem("hicareer.workflow_id");
    if (!workflowId) { status.innerHTML = '<span class="result-label">안내</span><h3>분석 workflow가 없습니다.</h3><p>진단에서 PDF를 제출하고 metadata를 확정한 뒤 다시 방문하세요.</p>'; return; }
    try {
      const response = await fetch("/api/workflows/" + encodeURIComponent(workflowId) + "/report", { cache: "no-store", headers: { "Accept": "application/json" } });
      const report = await response.json();
      if (!response.ok) throw new Error(report.error || "리포트를 불러오지 못했습니다.");
      render(report);
    } catch (error) { status.classList.add("caution-card"); status.innerHTML = '<span class="result-label">오류</span><h3>리포트를 불러오지 못했습니다.</h3><p>' + escapeHtml(error.message) + '</p><a class="button secondary" href="diagnosis.html">진단으로 돌아가기</a>'; }
  }
  load();
})();
