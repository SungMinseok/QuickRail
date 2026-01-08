# MVP 체크리스트 (설계 문서 기준) — 현재 구현 상태 분류

본 문서는 **사내 QA 툴 MVP 설계 문서**를 기준으로,  
현재 구현 상태를 **완료 / 부분 완료 / 미구현**으로 분류하고  
미구현 항목에 대해 **우선순위 기반 Phase 계획**을 정리한다.

---

## ✅ 완료 (사용 가능 수준)

### 인증 / Auth
- [x] 로그인 / 로그아웃 / 회원가입
- [x] `GET /api/me` (현재 사용자 정보)

### 프로젝트 / Project
- [x] 프로젝트 목록 / 생성 / 수정 / 삭제  
  - 삭제는 Super Admin 제한
- [x] 프로젝트 복제

### 유저 / User (관리 기능 일부)
- [x] 사용자 목록 조회
- [x] role / 활성화 수정
- [x] 사용자 삭제  
  - Super Admin 전용 API / 화면

### 섹션 트리 / Section
- [x] 트리 구조 (최대 4단계)
- [x] 생성 / 수정 / 삭제
- [x] 정렬 (order)

### 테스트 케이스 / Test Case
- [x] 생성 / 조회 / 수정 (인라인 autosave)
- [x] 복사
- [x] 섹션 이동 (`section_id` 변경)
- [x] 아카이브 / 복원 (삭제 대신 상태 변경)
- [x] 검색 / 필터  
  - 텍스트 / 태그 / 우선순위 / 정렬
- [x] 태그 관리
- [x] CSV / Excel Import  
  - 미리보기 → 컬럼 매핑 → 확정
  - 섹션 자동 생성  
  - (설계 문서 optional이지만 구현 완료)

### 테스트 런 / Test Run + 실행
- [x] 런 생성 / 목록 / 상세
- [x] 런 종료 / 재오픈
- [x] 런 실행 화면  
  - 케이스 목록 + 상세 + 결과 입력
- [x] 결과 기록 / 조회 / 히스토리
- [x] 런 결과 초기화
- [x] 첨부파일 업로드 / 다운로드

### 리포트 (기본)
- [x] 프로젝트 대시보드
  - 최근 런
  - 결과 카운트 / 진행률

---

## ⚠️ 부분 완료  
(기능은 있으나 설계 MVP 요구와 **불일치 또는 누락**)

### 역할 / RBAC
- [~] 현재 역할 구조  
  - `admin / author / runner`
- [~] 설계 기준 역할  
  - `Admin / Lead / Tester / Viewer`
- [~] 역할 매핑 및 권한 체계 불일치

### 실행 결과 상태값
- [~] 설계 상태값  
  - `NotRun / Pass / Fail / Blocked / Skipped`
- [~] 현재 상태값  
  - `pass / fail / blocked / retest / na`
- [~] `NotRun`은 결과 없음으로 암묵 처리 중

### 런 스냅샷 / 추적성
- [~] `RunCase` 엔터티는 존재
- [~] `case_version_snapshot` 없음
- [~] 테스트 케이스 수정 시  
  과거 런에서 “당시 버전” 추적이 어려움

### 감사 로그 / AuditLog
- [~] 모델은 존재
- [~] 실제 create / update / move / close 등에 대한  
  로그 기록 및 조회 플로우 없음

---

## ❌ 미구현  
(설계 MVP 기준 **핵심 공백**)

### Build / 빌드 라벨
- [ ] Test Run에 `build_label` (또는 Build 엔터티) 없음

### Run Case 할당 / 개인 작업 흐름
- [ ] `RunCase.assignee` 없음
- [ ] “테스터별 할당” 및 “내 할당 케이스” 뷰 없음

### 런 생성 시 케이스 추가 UX
- [ ] 섹션 기반 추가 (include children)
- [ ] 태그 / 검색 기반 선택 추가
- [ ] bulk add / bulk assign
- [ ] round-robin assign
- [ ] 현재는 `case_ids`로만 생성 가능

### 버그 링크
- [ ] Fail / Blocked 시 bug link 저장 불가
- [ ] JIRA Key / URL 표시 및 관리 없음

### 리포트 고도화 + CSV Export
- [ ] 런 리포트  
  - 섹션별 / 테스터별 breakdown 없음
- [ ] `export.csv` 없음  
  - 현재 CSV는 케이스 import 전용

---

## 🚧 미구현 항목 우선순위 (5단계)

### ✅ Phase 1 — MVP 수용 기준에서 "막히는 구멍" 메우기 (완료!)
- [x] Run에 `build_label` 추가
  - DB 필드 추가 완료
  - 런 생성 UI에 입력 필드 추가
  - 런 목록 및 실행 페이지에 표시
- [x] Result에 `bug_links` 추가
  - DB 필드 추가 완료
  - 결과 입력 UI에 입력 필드 추가
  - 결과 히스토리에 표시
- [x] 런 결과 CSV Export
  - `GET /api/runs/:id/export.csv` API 구현
  - UI 버튼 제공 (📥 CSV 내보내기)
  - UTF-8 BOM 포함 (Excel 호환)
- [x] 케이스 버전 + 런 스냅샷 최소 구현
  - `Case.version` 필드 추가 (default=1)
  - 케이스 수정 시 버전 자동 증가
  - `RunCase.case_version_snapshot` 저장
  - 런 포함 시점의 `title / steps / expected` 텍스트 스냅샷 저장
- [x] 결과 상태값 정리
  - 기존: `pass / fail / blocked / retest / na`
  - 추가: `notrun / skipped` (모델 지원)
  - NotRun은 결과 없음으로 처리

**완료 날짜**: 2026-01-05  
**마이그레이션**: `e8323c1b7b0f_phase_1_add_build_label_bug_links_.py`  
**상세 문서**: `design/phase1_completion_summary.md`

### Phase 2 — 실제 운영 워크플로우 완성 (할당 / 내 작업)
- `RunCase.assignee` 추가
- bulk assign UI
- “My assigned cases” 화면 / API
- 런 대시보드에 assignee별 진행 / 결과 요약

### Phase 3 — 런 구성 UX 고도화
- 런 생성 위저드 강화
- 섹션 트리 선택 (include children)
- 태그 필터 / 검색 기반 케이스 담기
- `AddCases / RemoveCases` API
- 섹션별 진행 / Pass-Fail breakdown 리포트

### Phase 4 — RBAC 정돈 + 런 잠금 규칙
- 역할 체계 통합  
  - `Admin / Lead / Tester / Viewer`
- 서버 사이드 권한 enforce 일원화
- 런 Close 시 정책 정의
  - 편집 가능 여부
  - 결과 입력 예외 규칙

### Phase 5 — 감사 로그 / 히스토리 / 품질 (운영 안정화)
- AuditLog 실제 기록
- AuditLog 조회 화면
- Execution history를 append-only 구조로 정리
  - (현재 5분 이내 업데이트 로직 재검토)
- 성능 / 사용성 보강
  - 케이스 10k 기준 페이징 / 인덱스 / 캐시
  - (선택) 실시간 업데이트 (폴링 / WebSocket)

---

## 📌 Next Step (Optional)

Phase 1을 기준으로 다음 항목까지 세분화 가능:
- DB Migration 단위
- API 추가 / 변경 목록
- 화면(UI) 변경 포인트
- 기능별 완료 기준(Definition of Done)

필요 시 **Phase 1을 실행 가능한 티켓 단위**로 다시 정리 가능.
