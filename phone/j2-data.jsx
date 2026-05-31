/* j2-data.jsx — domain data + simulated run timeline */

const J2_TASK = "Build a SaaS REST API with JWT auth and user management";

const J2_AGENTS = {
  plan:     { key: "plan",     name: "Planner",  model: "Gemma-4",  role: "decomposition" },
  backend:  { key: "backend",  name: "Backend",  model: "Claude",   role: "api + data" },
  frontend: { key: "frontend", name: "Frontend", model: "Gemini",   role: "ui" },
  iac:      { key: "iac",      name: "IaC",      model: "Claude",   role: "infra" },
  qa:       { key: "qa",       name: "QA",       model: "GPT",      role: "verification" },
};

const J2_NODES = [
  { id: "input",    label: "Request",  sub: "you",       col: 0, row: 0, kind: "io" },
  { id: "plan",     label: "Planner",  sub: "Gemma-4",   col: 1, row: 0, kind: "agent" },
  { id: "backend",  label: "Backend",  sub: "Claude",    col: 2, row: 0, kind: "agent" },
  { id: "frontend", label: "Frontend", sub: "Gemini",    col: 2, row: 1, kind: "agent" },
  { id: "iac",      label: "IaC",      sub: "Claude",    col: 2, row: 2, kind: "agent" },
  { id: "qa",       label: "QA",       sub: "GPT",       col: 3, row: 1, kind: "agent" },
  { id: "done",     label: "Shipped",  sub: "verified",  col: 4, row: 1, kind: "io" },
];

const J2_EDGES = [
  ["input", "plan"],
  ["plan", "backend"], ["plan", "frontend"], ["plan", "iac"],
  ["backend", "qa"], ["frontend", "qa"], ["iac", "qa"],
  ["qa", "done"],
];

const J2_FILES = [
  { agent: "backend",  path: "migrations/001_users.sql",  lines: 24 },
  { agent: "backend",  path: "app/auth.py",               lines: 96 },
  { agent: "backend",  path: "app/users.py",              lines: 71 },
  { agent: "frontend", path: "web/login.html",            lines: 58 },
  { agent: "frontend", path: "web/dashboard.html",        lines: 110 },
  { agent: "frontend", path: "web/app.js",                lines: 142 },
  { agent: "iac",      path: "Dockerfile",                lines: 19 },
  { agent: "iac",      path: "fly.toml",                  lines: 27 },
  { agent: "qa",       path: "tests/test_auth.py",        lines: 88 },
];

const J2_TIMELINE = [
  { wait: 300,  running: "plan", done: ["input"],
    say: { role: "jarvis", text: "On it. Decomposing the task with Gemma-4 and mapping out a dependency graph." },
    tokens: 1840, cost: 0.0003 },

  { wait: 2200, running: ["backend", "frontend", "iac"], done: ["plan"],
    say: { role: "jarvis", text: "Plan ready — 4 subtasks across Backend, Frontend and IaC. Backend runs first as the others depend on its API contract; QA verifies everything at the end." },
    plan: [
      "Design users schema + JWT auth endpoints",
      "Build login & dashboard UI wired to the API",
      "Containerise and prepare deploy config",
      "Verify contracts and write integration tests",
    ],
    tokens: 5210, cost: 0.0011, tab: "plan" },

  { wait: 2600, doneOne: "backend",
    say: { role: "jarvis", text: "Backend done. Users table, JWT auth and the user-management endpoints are in — 3 files written." },
    tokens: 12400, cost: 0.0021, tab: "files" },

  { wait: 1700, doneOne: "frontend",
    say: { role: "jarvis", text: "Frontend done. Login and dashboard are wired to the live auth API." },
    tokens: 18900, cost: 0.0030 },

  { wait: 1500, doneOne: "iac", running: "qa",
    say: { role: "jarvis", text: "Infra packaged. Handing the whole build to QA for verification." },
    tokens: 22600, cost: 0.0036, tab: "preview" },

  { wait: 2400, doneOne: "qa",
    say: { role: "jarvis", text: "QA passed — 12 integration tests green, all API contracts honoured." },
    tokens: 27800, cost: 0.0042 },

  { wait: 1200, doneOne: "done",
    say: { role: "jarvis", text: "Shipped. 9 files, 4 agents, $0.0042 total. I've indexed the API contracts to memory so the next session starts with full context. Want me to deploy it?" },
    done2: true },
];

const J2_SUGGESTIONS = [
  "Build a SaaS REST API with JWT auth",
  "Add Stripe billing to my dashboard",
  "Scaffold a Next.js marketing site",
  "Write integration tests for the auth flow",
];

const J2_RUNS = [
  { task: "Build a SaaS REST API with JWT auth and user management", when: "Active now", status: "running", files: 9, cost: "0.0042", agents: 4 },
  { task: "Add real-time presence to the chat app", when: "2 hours ago", status: "done", files: 6, cost: "0.0031", agents: 3 },
  { task: "Migrate Postgres schema to multi-tenant", when: "Yesterday", status: "done", files: 4, cost: "0.0028", agents: 2 },
  { task: "Generate an admin analytics dashboard", when: "Yesterday", status: "done", files: 11, cost: "0.0055", agents: 4 },
  { task: "Set up CI/CD with preview deploys", when: "May 27", status: "done", files: 7, cost: "0.0039", agents: 3 },
  { task: "Refactor payments service into modules", when: "May 26", status: "failed", files: 0, cost: "0.0009", agents: 1 },
];

const J2_MEMORY = [
  { kind: "contract", title: "POST /auth/login → { token, user }", note: "JWT, 24h expiry · HS256", from: "Backend · today" },
  { kind: "contract", title: "GET /users/me → User", note: "Bearer auth required", from: "Backend · today" },
  { kind: "decision", title: "Auth via short-lived JWT, no sessions", note: "Stateless; refresh handled client-side", from: "Planner · today" },
  { kind: "schema",   title: "users(id, email, pw_hash, created_at)", note: "email unique index", from: "Backend · today" },
  { kind: "decision", title: "Deploy target: Fly.io, single region", note: "iad · scale-to-zero off", from: "IaC · today" },
  { kind: "contract", title: "Presence channel: ws /presence", note: "heartbeat 20s", from: "Backend · 2h ago" },
];

Object.assign(window, {
  J2_TASK, J2_AGENTS, J2_NODES, J2_EDGES, J2_FILES,
  J2_TIMELINE, J2_SUGGESTIONS, J2_RUNS, J2_MEMORY,
});
