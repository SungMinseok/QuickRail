```md
# Flask 기반 TestRail-lite (User-first) — Cursor Agent용 스펙(MD)

목표: TestRail 유사 기능을 제공하되, **사용자 입장에서 클릭/이동/입력 부담을 최소화**한 QA 테스트케이스/런/결과 관리 웹앱을 Flask로 구현한다.  
원칙: **MVP는 “케이스 관리 + 런 생성 + 실행(체크) + 리포트”** 4가지만 완성해도 실제 운영 가능해야 한다.

---

## 0. 핵심 UX 원칙(반드시 지킬 것)

- **2-pane 기본 레이아웃**: 좌측은 Section 트리, 우측은 Case 리스트/편집
- **인라인 편집 + 자동 저장(Auto-save)**: 상세 페이지 이동 최소화
- **Quick Add**: 케이스는 “제목만 입력 후 Enter”로 즉시 생성(나머지는 나중에)
- **키보드 중심 Run 실행 UX**: 클릭 최소화, 핫키 제공
- **고급 필드는 숨김**: 기본 화면은 단순(필수 6~8개 필드만)
- **검색 중심**: 상단 통합 검색(케이스/태그/섹션/런)
- **실패 입력 최적화**: Fail 선택 시 코멘트/첨부 입력 영역 자동 펼침 및 포커스 이동
- **Undo(되돌리기)**: 최근 변경 1~3단계라도 제공(최소: 마지막 저장 전 상태 복구)

---

## 1. 범위(Scope) & 단계별 목표

### Phase 1 (MVP, 1차 출시)
- Auth (로그인)
- Project / Section(트리) / Case CRUD
- Tags / Search / Filters
- Test Run 생성(필터 기반) + 실행(결과 기록)
- 기본 리포트(진행률/Pass rate)

### Phase 2 (TestRail 대비 편의성 핵심)
- 런 템플릿(저장된 필터/셋)
- 키보드 핫키 고도화 & “다음 미실행 자동 이동”
- 중복 감지(제목 기반)
- “최근 실패 Top / 오래된 케이스” 운영 대시보드

### Phase 3 (확장)
- API / Webhook
- 이슈 트래커(예: Jira) 연동
- flaky/재시도 추적, 소유자 자동 할당

---

## 2. 데이터 모델(최소 스키마)

DB: SQLite(개발) → Postgres(운영) 전환 가능하도록 ORM(예: SQLAlchemy) 사용.

### 2.1 User
- id (PK)
- email (unique)
- name
- password_hash
- role: `admin | author | runner`
- created_at, updated_at

### 2.2 Project
- id
- name
- description (optional)
- created_at, updated_at

### 2.3 Section (트리)
- id
- project_id (FK)
- parent_id (nullable, self FK)
- name
- order_index (for manual sort)
- created_at, updated_at

### 2.4 Case
- id
- project_id (FK)
- section_id (FK)
- title
- steps (text, optional)
- expected_result (text, optional)
- priority: `P0|P1|P2|P3` (default P2)
- owner_id (FK User, nullable)
- status: `active|archived` (default active)
- created_at, updated_at

### 2.5 Tag
- id
- project_id (FK)
- name (lowercase unique per project)

### 2.6 CaseTag (M2M)
- case_id (FK)
- tag_id (FK)

### 2.7 Run
- id
- project_id (FK)
- name
- description (optional)
- created_by (FK User)
- run_type: `smoke|regression|hotfix|custom` (optional)
- is_closed (bool default false)
- created_at, updated_at

### 2.8 RunCase (스냅샷)
- id
- run_id (FK)
- case_id (FK)
- order_index (for run execution order)
- created_at

### 2.9 Result
- id
- run_id (FK)
- case_id (FK)
- executor_id (FK User)
- status: `pass|fail|blocked|retest|na`
- comment (text nullable)
- created_at

> NOTE: RunCase는 “런 생성 시점의 포함 케이스”를 보장하는 스냅샷 역할.  
> 케이스가 이후 수정돼도 런에 포함된 케이스 목록은 유지.

### 2.10 Attachment (옵션/Phase1에 포함 가능)
- id
- result_id (FK)
- file_path (or blob ref)
- original_name
- created_at

### 2.11 AuditLog (Phase2)
- id
- entity_type (`case|section|run`)
- entity_id
- actor_id
- action (`create|update|delete|move|archive`)
- diff_json (optional)
- created_at

---

## 3. 핵심 기능 요구사항(Functional Requirements)

### 3.1 인증/권한
- 로그인/로그아웃
- Role:
  - admin: 모든 권한
  - author: 케이스/섹션/런 생성 및 수정 가능
  - runner: 런 실행/결과 기록 가능(케이스 편집 제한)

### 3.2 Project
- 프로젝트 목록/생성/선택
- 기본 프로젝트 홈 = “케이스 관리 화면(2-pane)”

### 3.3 Section 트리
- 트리 표시(좌측)
- 섹션 생성/수정/삭제
- 드래그 앤 드롭 이동 + order_index 갱신
- 섹션 클릭 시 해당 섹션의 케이스 필터링

### 3.4 Case 관리(핵심)
- 리스트(우측)
  - 컬럼: Title, Priority, Tags, Owner, Updated_at
- Quick Add:
  - 입력창에 제목 입력 후 Enter → 즉시 생성
  - 생성 후 리스트 최상단에 표시
- 인라인 편집:
  - 제목/우선순위/태그/오너는 리스트에서 즉시 변경
  - steps/expected_result는 우측 하단 편집 패널(또는 슬라이드 패널)에서 편집
- Auto-save:
  - 입력 중 일정 debounce(예: 600ms) 후 저장
  - 저장 상태 표시(“Saving…/Saved”)
- Archive:
  - 삭제 대신 아카이브(기본 필터에서 숨김)

### 3.5 Tags/검색/필터
- 상단 통합 검색:
  - title/steps/expected_result/tag/owner/section name 검색(기본은 title+tag)
- 필터:
  - Priority, Tags(멀티), Owner, Updated time (최근 변경)
- 즐겨찾기 필터(Phase2):
  - 자주 쓰는 필터 조합 저장/불러오기

### 3.6 Run 생성(핵심)
- Run 생성 UI:
  - Run name 자동 제안(예: `YYYY-MM-DD Regression`)
  - 포함 케이스 선택 방식:
    1) 현재 필터 결과 전체 포함
    2) 체크박스 선택 포함
- 생성 시 RunCase 스냅샷 생성
- Run 목록:
  - open runs / closed runs
  - 진행률(미실행/전체) 표시

### 3.7 Run 실행(핵심 UX)
Run 실행 화면 구성:
- 좌측: RunCase 목록(상태 pill 표시)
- 우측: 현재 케이스 상세 + 결과 입력

키보드 핫키(Phase1부터):
- `j/k` : 다음/이전 케이스 이동
- `1` Pass
- `2` Fail (Fail 선택 시 코멘트 입력 포커스)
- `3` Blocked
- `4` Retest
- `5` NA
- `n` : 다음 미실행 케이스로 이동
- `/` : 검색 포커스

동작 규칙:
- 결과 입력 즉시 저장
- Fail이면 comment 필드 필수(옵션: “사유 없음” 빠른 입력 버튼)
- 첨부 업로드(이미지/zip/log) 지원(최소 1개)

### 3.8 리포트(Phase1)
- Run 상세에 통계:
  - Pass/Fail/Blocked/Retest/NA 카운트
  - Pass rate(%)
  - 진행률(완료/전체)
- Project 대시보드:
  - 최근 10개 Run 요약
  - 최근 실패 Top 10 케이스(Phase2)

---

## 4. TestRail 불편 개선(명시적 개선 항목)

- [필수] 상세 페이지 이동 최소화: 인라인/패널 편집으로 끝
- [필수] 런 생성 단순화: 필터 결과를 그대로 런으로 만들기
- [필수] 실행 화면 클릭 제거: 키보드 핫키 + 자동 이동
- [권장] 중복 케이스 증가 방지:
  - Case 생성 시 동일/유사 제목 Top5 제안(Phase2)
- [권장] 운영 지표 중심:
  - “오래된 케이스(예: 90일 미수정)”, “실패 많은 케이스” 표시

---

## 5. API 설계(REST, 최소)

### Auth
- POST `/api/auth/login`
- POST `/api/auth/logout`
- GET  `/api/me`

### Project
- GET `/api/projects`
- POST `/api/projects`
- GET `/api/projects/<id>`

### Section
- GET `/api/projects/<pid>/sections`
- POST `/api/projects/<pid>/sections`
- PATCH `/api/sections/<id>` (rename, parent move, order_index)
- DELETE `/api/sections/<id>` (soft delete or restrict)

### Case
- GET `/api/projects/<pid>/cases` (query: section_id, q, tags, priority, owner, status)
- POST `/api/projects/<pid>/cases` (Quick Add 포함)
- GET `/api/cases/<id>`
- PATCH `/api/cases/<id>` (inline edit + autosave)
- POST `/api/cases/<id>/archive`
- POST `/api/cases/<id>/unarchive`

### Tag
- GET `/api/projects/<pid>/tags`
- POST `/api/projects/<pid>/tags` (자동 생성 허용)
- DELETE `/api/tags/<id>` (옵션)

### Run
- GET `/api/projects/<pid>/runs`
- POST `/api/projects/<pid>/runs` (body: name, description, case_ids or filter_snapshot)
- GET `/api/runs/<id>`
- POST `/api/runs/<id>/close`
- POST `/api/runs/<id>/reopen` (옵션)

### Run Execution
- GET `/api/runs/<rid>/cases` (RunCase 목록 + latest result)
- POST `/api/runs/<rid>/results` (case_id, status, comment)
- GET `/api/runs/<rid>/results` (optional)

### Attachment
- POST `/api/results/<result_id>/attachments` (multipart)
- GET  `/api/attachments/<id>` (권한 체크)

---

## 6. UI 페이지(라우트) 제안

- `/login`
- `/projects`
- `/p/<project_id>/cases`
  - 좌측 Section 트리
  - 우측 Case 리스트 + 편집 패널
- `/p/<project_id>/runs`
  - Run 목록 + 생성 버튼
- `/runs/<run_id>`
  - Run 실행(핫키)

---

## 7. 기술 스택 제안(Flask 기준)

- Backend: Flask + SQLAlchemy + Flask-Login(또는 JWT)
- DB: SQLite(dev) / Postgres(prod)
- Migration: Alembic
- Frontend:
  - 간단히: Jinja + HTMX(권장: 빠르게 인라인 편집/부분 갱신)
  - 또는: React/Vue (원하면 API-first로)
- File upload: local storage(dev) + S3 compatible(prod) 옵션
- Search:
  - Phase1: SQL LIKE + tag join
  - Phase2: SQLite FTS5 또는 Postgres full-text

---

## 8. 비기능 요구사항(Non-Functional)

- 반응성: 주요 액션(결과 저장/인라인 편집)은 200~400ms 체감 목표
- 에러 처리:
  - 저장 실패 시 토스트 + 재시도 버튼
- 감사 로그(Audit):
  - 최소: 케이스 수정자/수정시각 추적
- 보안:
  - 프로젝트 단위 접근 제한(최소 role 기반)
- 테스트:
  - API 단위 테스트 + 간단 E2E(런 실행 플로우)

---

## 9. “Cursor Agent에게 지시” (구현 우선순위 가이드)

1) DB 모델/마이그레이션 작성  
2) Auth + Project/Section/Case CRUD API  
3) 2-pane 케이스 화면(HTMX 인라인 편집 + autosave)  
4) Run 생성(필터 기반 포함) + RunCase 스냅샷  
5) Run 실행 화면(핫키, 결과 저장, 다음 미실행 이동)  
6) 리포트(진행률, pass rate)  
7) (Phase2) 템플릿/중복 감지/운영 대시보드

---

## 10. 완료 기준(Definition of Done)

- Quick Add로 케이스 10개를 1분 내 생성 가능
- 필터 결과로 런 생성이 2클릭 이내
- 런 실행에서 키보드만으로 20개 케이스 Pass 처리 가능
- Fail 선택 시 코멘트 입력이 자동으로 열리고 저장됨
- Run에서 진행률/Pass rate가 즉시 업데이트됨
- 섹션 이동/정렬이 드래그로 가능하며 케이스 필터가 정상 동작

---
```
## 11. Excel / CSV Import & Export 기능

목표:  
- 기존 TestRail / Excel 기반 테스트케이스를 **마이그레이션 비용 없이** 가져오기  
- QA/기획/외주 인력이 **엑셀로 편집 → 다시 업로드**하는 흐름 지원  
- 구조는 유지하되, **실패 가능성 최소 + UX 단순화**

---

## 11.1 Import (엑셀 / CSV → Test Case)

### 지원 포맷
- `.xlsx` (우선)
- `.csv` (UTF-8, comma-separated)

### Import 대상
- Case만 1차 대상 (Run/Result는 Phase2 이상에서 고려)
- Import 시 자동 생성/매핑:
  - Section
  - Tag
  - Owner(옵션)

---

### 기본 Import 컬럼 정의 (필수/권장)

| Column | 필수 | 설명 |
|------|------|------|
| Section | O | 섹션 경로 (예: `Login > Invalid Case`) |
| Title | O | 테스트케이스 제목 |
| Steps | X | 테스트 스텝 |
| Expected Result | X | 기대 결과 |
| Priority | X | P0~P3 (없으면 P2) |
| Tags | X | `tag1,tag2` 형식 |
| Owner | X | 사용자 이메일 또는 이름 |

> **중요 원칙**  
> - 컬럼 순서는 자유  
> - 컬럼명은 대소문자 무시  
> - 미존재 컬럼은 무시  
> - 필수 컬럼(Section, Title) 누락 시 해당 행 skip + 에러 리포트

---

### Section 처리 규칙
- `Section` 컬럼은 `>` 또는 `/` 로 계층 표현 허용
  - 예: `Payment > Card > Fail`
- 존재하지 않는 Section은 **자동 생성**
- 공백은 trim, 연속 공백/중복 separator 자동 정리

---

### Tag 처리 규칙
- `Tags` 컬럼:
  - `tag1, tag2, tag3`
- 미존재 Tag는 자동 생성
- 소문자 정규화(`Login` → `login`)

---

### Owner 매핑
- Owner 값이:
  - 이메일 → User.email 매칭
  - 이름 → User.name 매칭
- 매칭 실패 시:
  - owner = null
  - Import 결과 리포트에 warning 기록

---

### Import UX 흐름

1. **파일 업로드**
   - `/p/<project_id>/cases/import`
2. **컬럼 매핑 화면**
   - 시스템 컬럼 ↔ 엑셀 컬럼 drag/select 매핑
   - 자동 추론 + 수정 가능
3. **미리보기(Preview)**
   - 최초 N행(예: 10행) 표시
   - 생성될 Section/Tag 개수 표시
4. **실행**
   - Import 실행
   - 성공/실패/스킵 요약 리포트 표시
5. **결과 로그 다운로드**
   - 실패 행 CSV 다운로드 제공

---

### Import 에러 처리 정책

- 전체 중단 ❌  
- **행 단위 부분 성공 허용**
- 결과 요약:
  - Total rows
  - Imported
  - Skipped (이유 포함)
  - Warnings

---

## 11.2 Export (Test Case → Excel / CSV)

### Export 대상
- Case
- (Phase2) Run + Result

### Export 범위 선택
- 현재 필터 결과 전체
- 선택한 Case만
- 특정 Section 하위 전체

---

### Export 포맷 컬럼 (기본)

| Column |
|------|
| Case ID |
| Section |
| Title |
| Steps |
| Expected Result |
| Priority |
| Tags |
| Owner |
| Status |
| Created At |
| Updated At |

- Section은 full path(`Login > Invalid`)로 출력
- Tags는 `,` 로 join
- 줄바꿈 있는 필드는 Excel-safe 처리

---

### Excel Export UX
- `/p/<project_id>/cases/export`
- 옵션:
  - Format: `xlsx / csv`
  - Include archived cases (checkbox)
  - Include empty fields (checkbox)

---

## 11.3 Import 중복 처리 정책

### 기본 정책 (Phase1)
- **완전 신규 생성만 지원**
- 기존 Case 업데이트 ❌

### Phase2 확장(옵션)
- `Case ID` 컬럼 존재 시:
  - 동일 ID 존재 → Update
  - 미존재 → Create
- `Title + Section` 동일 시 중복 경고

---

## 11.4 API 설계 (Import / Export)

### Import
POST `/api/projects/<pid>/cases/import`
- multipart/form-data
  - file
  - options:
    - dry_run (bool)
    - create_missing_sections (default true)
    - create_missing_tags (default true)

### Export
GET `/api/projects/<pid>/cases/export`
- query:
  - format = xlsx | csv
  - section_id
  - tag
  - priority
  - include_archived

---

## 11.5 구현 가이드 (Cursor Agent용)

### Backend
- Excel: `openpyxl`
- CSV: Python csv module
- Import는 **transaction 단위로 row 처리**
- Preview는 실제 DB write 없이 parse-only(dry_run)

### Frontend
- Import:
  - 파일 업로드 → 컬럼 매핑 → Preview → 실행
- Export:
  - 현재 필터 조건 그대로 query string에 반영

---

## 11.6 완료 기준(Import/Export)

- TestRail CSV를 약간 수정해서 그대로 Import 가능
- 500~1,000 케이스 Import 시 타임아웃 없이 처리
- Import 실패 행에 대해 이유가 명확히 제공됨
- Export된 Excel을 수정 후 재-import 가능
- Section/Tag 구조가 손실 없이 유지됨

---
