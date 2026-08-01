const popularJobsContainer = document.querySelector("#popularJobs");
const jobFilters = document.querySelectorAll("[data-job-filter]");

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
  },
  {
    title: "Product Manager Intern",
    company: "모바일 서비스 스타트업",
    category: "product",
    location: "서울 · 인턴",
    deadline: "D-7",
    fit: 82,
    skills: ["UX Research", "기획", "데이터 해석"],
    reason: "대외활동·운영 경험을 프로덕트 언어로 바꾸기 좋음",
    url: "diagnosis.html",
  },
  {
    title: "Backend Developer Rookie",
    company: "핀테크 플랫폼",
    category: "dev",
    location: "서울 · 신입",
    deadline: "D-18",
    fit: 80,
    skills: ["API", "DB", "협업"],
    reason: "서버 프로젝트와 장애 해결 경험을 강조하기 좋은 공고",
    url: "diagnosis.html",
  },
  {
    title: "Growth Marketer Intern",
    company: "에듀테크 기업",
    category: "product",
    location: "원격 가능",
    deadline: "D-21",
    fit: 77,
    skills: ["콘텐츠", "실험", "분석"],
    reason: "캠페인·대외활동 경험을 수치 성과로 확장하기 좋음",
    url: "diagnosis.html",
  },
];

const CACHE_KEY = "hicareer-popular-jobs";
const CACHE_TTL = 10 * 60 * 1000;

function getCachedJobs() {
  try {
    const cached = JSON.parse(sessionStorage.getItem(CACHE_KEY));
    if (!cached || Date.now() - cached.savedAt > CACHE_TTL) return null;
    return cached.jobs;
  } catch {
    return null;
  }
}

function setCachedJobs(jobs) {
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify({ jobs, savedAt: Date.now() }));
  } catch {
    return;
  }
}

async function fetchPopularJobs() {
  const cachedJobs = getCachedJobs();
  if (cachedJobs) return cachedJobs;

  try {
    const response = await fetch("/api/jobs/popular?limit=6");
    if (!response.ok) throw new Error("Popular jobs API unavailable");
    const payload = await response.json();
    const jobs = Array.isArray(payload) ? payload : payload.jobs;
    if (!Array.isArray(jobs)) throw new Error("Unexpected jobs API response");
    setCachedJobs(jobs);
    return jobs;
  } catch {
    return fallbackJobs;
  }
}

function renderJobs(jobs, filter = "all") {
  const visibleJobs = filter === "all" ? jobs : jobs.filter((job) => job.category === filter);

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
          <a href="${job.url}">내 CV와 비교하기</a>
        </article>
      `,
    )
    .join("");
}

async function initializePopularJobs() {
  if (!popularJobsContainer) return;
  const jobs = await fetchPopularJobs();
  renderJobs(jobs);

  jobFilters.forEach((button) => {
    button.addEventListener("click", () => {
      jobFilters.forEach((filterButton) => filterButton.classList.remove("active"));
      button.classList.add("active");
      renderJobs(jobs, button.dataset.jobFilter);
    });
  });
}

initializePopularJobs();
