# In-house Game QA Tool — MVP Definition (for Cursor Implementation)

> Goal: **Ship a usable internal QA workflow** with the smallest feature set that still supports
> **test case authoring → test runs → execution results → bug linkage → basic reporting**.
>
> Non-goals for MVP: advanced analytics, automation integration, complex permissions, multi-tenant SaaS hardening.

---

## 1) MVP Scope Summary

### Must-have outcomes
- QA can **create and maintain Test Cases**
- QA Lead can create a **Test Run** for a build/release
- Testers can **execute** assigned cases and record results
- Failures can be **linked to Bugs** (or at minimum to external tracker URLs/keys)
- Leads can see **progress** (Pass/Fail/Blocked/Not Run) by run, section, tester

### Users / Roles (MVP)
- **Admin**: system setup, user management
- **QA Lead**: creates/locks runs, assigns cases and testers
- **Tester**: executes cases, records results, links bugs
- **Viewer** (optional for MVP): read-only access to runs and reports

> MVP permissions can be coarse: Admin/Lead/Testers (Viewer optional).

---

## 2) Core Data Model (Entities)

### 2.1 Project
- `id`, `name`, `key`
- `created_at`, `updated_at`

### 2.2 User
- `id`, `email`, `display_name`
- `role` = Admin | Lead | Tester | Viewer
- `is_active`

### 2.3 Test Suite / Section (hierarchy)
- `id`, `project_id`
- `name`
- `parent_id` (nullable) — for tree structure
- `sort_order`

### 2.4 Test Case
- `id` (human-friendly sequence optional: e.g., TC-000123)
- `project_id`
- `section_id`
- `title`
- `preconditions` (text, optional)
- `steps` (text) — keep as markdown/plain text for MVP
- `expected_result` (text)
- `tags` (string array)
- `priority` (P0/P1/P2/P3) — optional but recommended
- `status` (Active | Deprecated)
- `version` (int) — increments on edit
- `created_by`, `updated_by`, `created_at`, `updated_at`

### 2.5 Build
- `id`, `project_id`
- `name` (e.g., 1.3.0-rc1), `platform` (PC/Console/Mobile), optional
- `commit_hash` (optional), `branch` (optional)
- `created_at`

> If you already track builds elsewhere, Build can be a simple string field on Test Run instead.

### 2.6 Test Run
- `id`, `project_id`
- `name` (e.g., “1.3.0 RC1 Smoke”)
- `build_label` (string) or `build_id`
- `run_type` (Smoke | Regression | Feature | Hotfix)
- `status` (Draft | Active | Closed)
- `owner_user_id`
- `created_at`, `updated_at`
- `locked_at` (nullable) — when closed/locked

### 2.7 Run Case (Test Run Item)
Represents a Test Case included in a run.
- `id`, `run_id`, `test_case_id`
- `assignee_user_id` (nullable)
- `order` (int)
- `case_version_snapshot` (int) — snapshot test_case.version at inclusion time (important for traceability)

### 2.8 Execution Result (per Run Case)
- `id`, `run_case_id`
- `result` (NotRun | Pass | Fail | Blocked | Skipped)
- `executed_by_user_id` (nullable)
- `executed_at` (nullable)
- `comment` (text, optional)
- `evidence_urls` (string array, optional)
- `bug_links` (string array, optional) — e.g., ["JIRA-123", "https://..."]
- `duration_seconds` (optional)

> Implementation simplification: store a single “current” execution per run_case (overwrite with history OFF).
> Better: append-only history table, and expose only latest as current.

### 2.9 Audit Log (recommended for MVP)
- `id`, `project_id`
- `entity_type`, `entity_id`
- `action` (CREATE/UPDATE/DELETE/STATUS_CHANGE)
- `summary` (text)
- `actor_user_id`
- `created_at`

---

## 3) MVP User Flows

### 3.1 Authoring Test Cases
- Create/edit test case
- Move test case to another section
- Deprecate test case (don’t delete by default)
- Search/filter by title/tags/ID/section/status

### 3.2 Creating a Test Run
- Lead selects `project + build_label + run_type`
- Add cases to run:
  - by section selection (include children)
  - by tag filter
  - manual add by ID/search
- Assign testers to run cases (bulk assign by section/tag + round-robin optional)

### 3.3 Executing a Run
- Tester opens “My assigned cases” view
- For each case:
  - read steps/expected
  - set result (Pass/Fail/Blocked/Skipped)
  - add comment/evidence
  - add bug link(s) when Fail/Blocked
- Run overview updates in real time

### 3.4 Reporting
- Run summary:
  - counts by result
  - progress percent (executed/total)
  - breakdown by section and by assignee
- Export:
  - CSV export for run results (minimum)

---

## 4) MVP Screens (Minimal UI)

### Navigation
- Project switcher
- Left nav: Test Cases / Test Runs / Reports

### Test Cases
- List: search, filters (section, tag, status, priority)
- Detail: view + edit
- Create
- Section tree management (create/rename/reorder basic)

### Test Runs
- Run list (filter by status/build)
- Create run wizard (name/build/type → select cases → assign)
- Run dashboard (summary + table of run cases)
- Execution view (optimized for fast result entry)

### Reports
- “Latest runs” quick list
- Run report page (same as run dashboard, plus export)

---

## 5) MVP API (Suggested Endpoints)

> REST examples; GraphQL is also fine.

### Auth
- `POST /auth/login` (or SSO later; MVP can be simple email/password or company SSO stub)
- `GET /me`

### Projects / Users
- `GET /projects`
- `POST /projects` (admin)
- `GET /users` (admin/lead)
- `POST /users` (admin)
- `PATCH /users/:id` (role/active)

### Sections
- `GET /projects/:projectId/sections`
- `POST /projects/:projectId/sections`
- `PATCH /sections/:id`
- `POST /sections/:id/move` (parent/order)

### Test Cases
- `GET /projects/:projectId/testcases?search=&sectionId=&tag=&status=&priority=`
- `POST /projects/:projectId/testcases`
- `GET /testcases/:id`
- `PATCH /testcases/:id`
- `POST /testcases/:id/deprecate`
- `POST /testcases/import` (CSV) — optional for MVP but strongly recommended

### Test Runs
- `GET /projects/:projectId/runs?status=&build=`
- `POST /projects/:projectId/runs`
- `GET /runs/:id`
- `PATCH /runs/:id` (name/build/type/status)
- `POST /runs/:id/addCases` (by ids/section/tag)
- `POST /runs/:id/assign` (bulk assign)
- `POST /runs/:id/close` (lock)

### Execution
- `GET /runs/:id/cases?assignee=me&result=`
- `PATCH /runCases/:id/result` (set result/comment/bug_links/evidence)
- `GET /runs/:id/export.csv`

---

## 6) Key MVP Design Decisions (Do This to Avoid Rewrites)

### 6.1 Snapshot case version into run
- Store `case_version_snapshot` on Run Case to preserve traceability when cases change later.

### 6.2 Prefer “Deprecated” over hard delete
- Avoid breaking past runs and analytics.

### 6.3 Keep steps as plain text/markdown for MVP
- Avoid complex step editors until needed.

### 6.4 Results are per run_case (not per test_case)
- Same test case can appear in multiple runs with independent outcomes.

---

## 7) Non-Functional Requirements (MVP)

### Performance
- Test case list: p95 < 500ms for 10k cases with filters (use DB indexing)
- Run dashboard: p95 < 500ms for 2k run cases

### Reliability
- No data loss on refresh; optimistic UI is fine but must be consistent
- Basic DB backups (daily)

### Security
- RBAC enforced server-side
- Audit log for case/run edits (recommended)

---

## 8) Suggested Tech Stack (Cursor-friendly)

### Backend
- Node.js (NestJS/Express) or Python (FastAPI)
- PostgreSQL
- Prisma/TypeORM/SQLAlchemy

### Frontend
- React + TanStack Query
- Component library optional (MUI/Chakra/shadcn)

### Auth (MVP)
- Simple JWT + password OR company SSO stub (replace later)

---

## 9) MVP Milestones (Implementation Order)

1. Projects + Users + Roles
2. Sections tree + Test Case CRUD + Search
3. Test Run CRUD + Add cases to run + Assign
4. Execution flow + Result recording + Run dashboard
5. Bug links + CSV export
6. Audit log + basic admin tools

---

## 10) Acceptance Checklist (MVP “Done”)

- Admin can create project and users
- Lead can create sections and test cases
- Lead can create a run for a build, add cases, and assign testers
- Tester can complete assigned cases with Pass/Fail/Blocked/Skipped and add bug link
- Lead can view run progress and export results as CSV
- Past runs remain readable even if test cases are edited/deprecated later

---

## Appendix A) CSV Formats (Optional but Recommended)

### A.1 Test Case Import (columns)
- `section_path` (e.g., "Gameplay/Combat")
- `title`
- `preconditions`
- `steps`
- `expected_result`
- `tags` (comma-separated)
- `priority`
- `status`

### A.2 Run Result Export (columns)
- `run_id`, `run_name`, `build_label`, `run_status`
- `section_path`
- `test_case_id`, `test_case_title`, `case_version_snapshot`
- `assignee`, `result`, `executed_by`, `executed_at`
- `bug_links`, `comment`, `evidence_urls`
