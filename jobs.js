const popularJobsContainer = document.querySelector("#popularJobs");
const jobFilters = document.querySelectorAll("[data-job-filter]");
const jobSearchInput = document.querySelector("#jobSearchInput");
const jobSearchButton = document.querySelector("#jobSearchButton");
const jobSearchStatus = document.querySelector("#jobSearchStatus");

const fallbackJobs = [
  {
    title: "Junior AI Engineer",
    company: "헬스케어 AI 스타트업",
    category: "ai",
    location: "서울 · 하이브리드",
    deadline: "D-9",
    fit: 94,
    skills: ["Python", "LLM", "데이터 전처리"],
    reason: "프로젝트·논문·해커톤 경험을 강점으로 가져가기 좋은 공고",
    url: "diagnosis.html",
    source: "샘플",
  },
  {
    title: "Frontend Developer Intern",
    company: "B2B SaaS 기업",
    category: "dev",
    location: "판교 · 인턴",
    deadline: "D-12",
    fit: 89,
    skills: ["React", "TypeScript", "UI 구현"],
    reason: "배포 프로젝트와 GitHub 증거를 보여주기 좋은 포지션",
    url: "diagnosis.html",
    source: "샘플",
  },
  {
    title: "Data Analyst Assistant",
    company: "커머스 플랫폼",
    category: "ai",
    location: "서울 · 신입",
    deadline: "D-15",
    fit: 86,
    skills: ["SQL", "Dashboard", "A/B Test"],
    reason: "정량 성과와 문제 정의 역량을 만들기 좋은 공고",
    url: "diagnosis.html",
    source: "샘플",
  },
];

const CACHE_TTL = 10 * 60 * 1000;
let currentJobs = [];
let activeFilter = "all";
let searchTimer;
let activeRequestId = 0;

function getCacheKey(keyword) {
  return `hicareer-popular-jobs:${keyword}`;
}

function getCachedJobs(keyword) {
  try {
    const cached = JSON.parse(sessionStorage.getItem(getCacheKey(keyword)));
    if (!cached || Date.now() - cached.savedAt > CACHE_TTL) return null;
    return cached.jobs;
  } catch {
    return null;
  }
}

function setCachedJobs(keyword, jobs) {
  try {
    sessionStorage.setItem(getCacheKey(keyword), JSON.stringify({ jobs, savedAt: Date.now() }));
  } catch {
    return;
  }
}

function setStatus(message) {
  if (jobSearchStatus) jobSearchStatus.textContent = message;
}

function renderSkeleton() {
  popularJobsContainer.innerHTML = `
    <article class="job-card skeleton"></article>
    <article class="job-card skeleton"></article>
    <article class="job-card skeleton"></article>
  `;
}

async function fetchPopularJobs(keyword) {
  const normalizedKeyword = keyword.trim() || "AI 인턴";
  const cachedJobs = getCachedJobs(normalizedKeyword);
  if (cachedJobs) return cachedJobs;

  const response = await fetch(`/api/jobs/popular?limit=12&keyword=${encodeURIComponent(normalizedKeyword)}`);
  if (!response.ok) throw new Error("Popular jobs API unavailable");
  const payload = await response.json();
  const jobs = Array.isArray(payload) ? payload : payload.jobs;
  if (!Array.isArray(jobs)) throw new Error("Unexpected jobs API response");
  setCachedJobs(normalizedKeyword, jobs);
  return jobs;
}

function renderJobs(jobs, filter = "all") {
  const visibleJobs = filter === "all" ? jobs : jobs.filter((job) => job.category === filter);

  if (!visibleJobs.length) {
    popularJobsContainer.innerHTML = `
      <article class="empty-card">
        <h3>해당 필터의 공고가 아직 없어요.</h3>
        <p>다른 키워드로 검색하거나 전체 필터를 선택해보세요.</p>
      </article>
    `;
    return;
  }

  popularJobsContainer.innerHTML = visibleJobs
    .map(
      (job) => `
        <article class="job-card">
          <div class="job-card-top">
            <span class="fit high">Fit ${job.fit}</span>
            <span class="deadline">${job.deadline}</span>
          </div>
          <span class="job-source">${job.source || "HICAREER"}</span>
          <h3>${job.title}</h3>
          <p class="company">${job.company}</p>
          <p class="job-meta">${job.location}</p>
          <div class="skill-row">${job.skills.map((skill) => `<span>${skill}</span>`).join("")}</div>
          <p class="job-reason">${job.reason}</p>
          <a href="${job.url}" target="_blank" rel="noopener noreferrer">공고 보기</a>
        </article>
      `,
    )
    .join("");
}

async function runJobSearch() {
  if (!popularJobsContainer || !jobSearchInput) return;

  const requestId = ++activeRequestId;
  const keyword = jobSearchInput.value.trim() || "AI 인턴";
  renderSkeleton();
  setStatus(`“${keyword}” 공고를 실시간으로 검색 중입니다.`);

  try {
    const jobs = await fetchPopularJobs(keyword);
    if (requestId !== activeRequestId) return;
    currentJobs = jobs.length ? jobs : fallbackJobs;
    renderJobs(currentJobs, activeFilter);
    setStatus(`“${keyword}” 기준 ${currentJobs.length}개 공고를 불러왔습니다.`);
  } catch {
    if (requestId !== activeRequestId) return;
    currentJobs = [];
    popularJobsContainer.innerHTML = `
      <article class="empty-card">
        <h3>실시간 검색 백엔드가 연결되지 않았어요.</h3>
        <p><code>python3 server.py</code>로 실행해야 사람인·잡코리아 검색 결과가 표시됩니다.</p>
      </article>
    `;
    setStatus("정적 서버가 아니라 HICAREER 백엔드 서버로 접속해주세요.");
  }
}

function scheduleJobSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(runJobSearch, 450);
}

function initializePopularJobs() {
  if (!popularJobsContainer) return;

  jobFilters.forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.jobFilter;
      jobFilters.forEach((filterButton) => filterButton.classList.remove("active"));
      button.classList.add("active");
      renderJobs(currentJobs, activeFilter);
    });
  });

  jobSearchInput?.addEventListener("input", scheduleJobSearch);
  jobSearchButton?.addEventListener("click", runJobSearch);
  runJobSearch();
}

initializePopularJobs();
