# Phase 1 수정사항 요약

## 수정 날짜
2026-01-05

## 수정 배경
Phase 1 테스트 케이스 실행 중 발견된 버그 및 개선사항을 수정하였습니다.

---

## 1. Cases 페이지에 CSV Export 버튼 추가

### 문제
- [TC-P1-017] 테스트 중 Cases 페이지에 CSV Export 버튼이 없는 것을 발견

### 수정 내용
- **API 추가**: `/api/sections/<int:section_id>/cases/export.csv` 엔드포인트 생성
- **UI 추가**: Cases 페이지 우측 상단에 "📊 CSV 내보내기" 버튼 추가
  - 섹션 선택 시에만 버튼이 표시됨
  - 선택한 섹션과 모든 하위 섹션의 케이스를 CSV로 내보내기
- **CSV 형식**:
  - 컬럼: Section Path, Test Case ID, Test Case Title, Version, Priority, Steps, Expected Result, Tags, Created By, Created At
  - UTF-8 BOM 포함으로 Excel에서 한글 깨짐 방지
  - 파일명: `{섹션명}_cases_{날짜시간}.csv`

### 수정 파일
- `app/routes/api.py`: CSV export API 엔드포인트 추가
- `app/templates/main/cases.html`: CSV export 버튼 및 JavaScript 함수 추가

---

## 2. 런 스냅샷 버그 수정

### 문제
- [TC-P1-012] 케이스 타이틀 및 내용 변경 시, 완료된 런의 내용도 변경되는 버그
- 완료된 런의 케이스는 런 생성 시점의 값이 유지되어야 하는데, 원본 케이스가 변경되면 완료된 런에서도 변경된 내용이 표시됨

### 원인
- `/api/runs/<int:run_id>/cases` API에서 항상 현재 케이스 데이터(`rc.case.title`, `rc.case.steps` 등)를 반환
- 런 상태와 관계없이 실시간 데이터를 사용

### 수정 내용
- **API 로직 개선**: 런 상태에 따라 다른 데이터 반환
  ```python
  if run.status == 'closed':
      # 완료된 런: 스냅샷 데이터 사용
      case_title = rc.title_snapshot or rc.case.title
      case_steps = rc.steps_snapshot or rc.case.steps
      case_expected = rc.expected_result_snapshot or rc.case.expected_result
      case_version = rc.case_version_snapshot or rc.case.version or 1
  else:
      # 진행 중인 런: 현재 데이터 사용 (편의성)
      case_title = rc.case.title
      case_steps = rc.case.steps
      case_expected = rc.case.expected_result
      case_version = rc.case.version or 1
  ```
- **결과**: 
  - 완료된 런은 런 생성 시점의 스냅샷 유지
  - 진행 중인 런은 최신 케이스 내용 표시 (편의성)

### 수정 파일
- `app/routes/api.py`: `run_cases()` 함수 수정

---

## 3. 케이스 버전 표시 추가

### 요구사항
- 케이스 상세보기 모달에서 케이스 버전 표시
- 케이스 편집 모달에서 케이스 버전 표시
- 런 실행 페이지 우측 상세 영역 내 케이스 버전 표시

### 수정 내용

#### 3.1 케이스 상세/편집 모달
- 모달 제목 옆에 버전 배지 추가
- 스타일: 파란색 배지 (`v1`, `v2`, ...)
- 위치: 케이스 제목 우측

#### 3.2 런 실행 페이지
- 케이스 제목 옆에 버전 배지 추가
- 완료된 런: 스냅샷 버전 표시
- 진행 중인 런: 현재 버전 표시

#### 3.3 API 수정
- `/api/cases/<int:case_id>` GET 응답에 `version` 필드 추가
- `/api/runs/<int:run_id>/cases` GET 응답에 `case_version` 필드 추가

### 수정 파일
- `app/routes/api.py`: API 응답에 버전 정보 추가
- `app/templates/main/cases.html`: 모달에 버전 배지 추가
- `app/templates/main/run_execute.html`: 런 실행 페이지에 버전 배지 추가

---

## 4. 런 중 케이스 편집 정책 명확화

### 문제
- [TC-P1-010] 케이스 버전 관리 기능과 런 실행 중 케이스 편집 기능의 충돌
- 정책이 명확하지 않아 혼란 발생 가능

### 결정된 정책: 옵션 1
**진행 중인 런에서만 편집 허용, 완료된 런은 스냅샷 유지**

#### 진행 중인 런 (Status: Open)
- ✅ 케이스 편집 가능
- 편집 시 **원본 케이스** 수정 (버전 증가)
- 항상 **현재 케이스 데이터** 표시
- 다른 진행 중인 런들도 동일하게 업데이트된 내용 표시

#### 완료된 런 (Status: Closed)
- 🔒 케이스 편집 불가
- **런 생성 시점의 스냅샷** 표시
- 원본 케이스가 변경되어도 완료된 런은 불변

### 구현 확인
- `updateCaseField()` 함수에서 `isRunClosed` 체크 이미 구현됨
- 완료된 런에서 편집 시도 시 경고 메시지 표시

### UI 개선
- **진행 중인 런**: "💡 클릭하여 편집 가능 (원본 케이스에 반영됩니다)"
- **완료된 런**: "🔒 완료된 런 - 런 생성 시점의 케이스 내용 (v2)"
- 테스트 스텝/기대 결과에도 동일한 안내 메시지 추가

### 정책 문서
- `design/case_editing_policy.md` 생성
- 정책 상세, 사용 시나리오, 향후 개선 방안 문서화

### 수정 파일
- `app/templates/main/run_execute.html`: UI 안내 메시지 개선
- `design/case_editing_policy.md`: 정책 문서 생성

---

## 테스트 권장사항

### 1. CSV Export 테스트
1. Cases 페이지에서 섹션 선택
2. "📊 CSV 내보내기" 버튼 클릭
3. CSV 파일 다운로드 확인
4. Excel에서 열어 한글 깨짐 없는지 확인
5. 하위 섹션의 케이스들도 포함되었는지 확인

### 2. 런 스냅샷 테스트
1. 런 생성 (케이스 v1)
2. 런 완료
3. 원본 케이스 수정 (v1 → v2)
4. 완료된 런 다시 열기 → v1 내용 표시 확인
5. 새 런 생성 → v2 내용으로 스냅샷 생성 확인

### 3. 케이스 버전 표시 테스트
1. Cases 페이지에서 케이스 상세 모달 열기 → 버전 배지 확인
2. 케이스 내용 수정 → 버전 증가 확인
3. 런 실행 페이지에서 케이스 선택 → 버전 배지 확인
4. 완료된 런에서 스냅샷 버전 표시 확인

### 4. 런 중 케이스 편집 정책 테스트
1. 진행 중인 런에서 케이스 편집 → 성공 확인
2. 원본 케이스 버전 증가 확인
3. 다른 진행 중인 런에서 업데이트된 내용 확인
4. 런 완료 후 케이스 편집 시도 → 차단 확인
5. 완료된 런에서 스냅샷 유지 확인

---

## 관련 테스트 케이스
- [TC-P1-010]: 런 생성 후 케이스 내용 변경 시 완료된 런 스냅샷 유지 ✅
- [TC-P1-011]: 케이스 버전 증가 확인 ✅
- [TC-P1-012]: 완료된 런의 케이스 내용 불변성 확인 ✅
- [TC-P1-017]: Cases 페이지 CSV Export 버튼 ✅

---

## 다음 단계
- Phase 1 수정사항 테스트 완료 후 Phase 2 진행 검토
- Phase 2 주요 기능:
  - `RunCase.assignee` 추가 (테스터별 할당)
  - Bulk assign UI
  - "My assigned cases" 화면/API
  - 런 대시보드에 assignee별 진행/결과 요약


