# 원버튼 JIRA 이슈 등록 참고 문서 (JiraAutoWeb2)

목적: 다른 앱에서 “원버튼으로 JIRA 이슈 등록” 기능을 구현할 때, **이 프로젝트의 실제 동작 흐름/요청 바디/필드 매핑**을 그대로 참고할 수 있도록 정리합니다.

---

## 전체 아키텍처(요약)

- **Frontend**: `templates/index.html` + `static/js/app.js`
- **Backend**: `app.py` (Flask)
- **JIRA 연동**: `api/jira_api.py` (`JiraAPIClient`)

요청 흐름:

1. 사용자가 웹 폼 입력 → “이슈 생성” 클릭
2. 브라우저 JS가 폼 값을 JSON으로 구성해 `POST /api/issues` 호출
3. Flask가 요청 JSON을 받아 `JiraAPIClient.create_issue(issue_data)` 호출
4. `JiraAPIClient`가 요청 데이터를 JIRA REST v3 payload로 변환 후 `POST /rest/api/3/issue`
5. 성공 시 `issue_key` / `issue_url` 반환, 실패 시 필드별 에러를 파싱해 반환

---

## 원버튼 구현 시 “가장 중요한” 엔드포인트

### 1) 단건 이슈 생성 (실제 생성)

- **Endpoint**: `POST /api/issues`
- **Frontend 호출 위치**: `static/js/app.js`의 `createIssue()` → `fetch(API.ISSUES, ...)`
- **Backend 처리 위치**: `app.py`의 `create_issue()` → `JiraAPIClient.create_issue(issue_data)`

### 2) 이슈 생성 미리보기 (실제 생성 없음)

- **Endpoint**: `POST /api/issues/preview`
- **용도**: “지금 입력한 값이 실제로 어떤 JIRA payload로 변환되는지”를 그대로 확인
- **Backend**: `JiraAPIClient._convert_to_jira_format(issue_data)` 결과(payload)를 포함해 내려줌

### 3) 일괄 생성

- **Endpoint**: `POST /api/issues/batch`
- **Request**: `{ "issues": [issueData1, issueData2, ...] }`

---

## 프론트 → 서버로 보내는 Request Body (사실상 표준 스키마)

`static/js/app.js`의 `getFormData()`가 생성하는 JSON이 곧 이 앱의 표준입니다.

```json
{
  "summary": "필수 - 이슈 제목",
  "team": "선택 - Team(커스텀 필드)",
  "label": "선택 - 라벨1,라벨2 (쉼표구분 문자열)",
  "priority": "선택 - 예: High",
  "severity": "선택 - 예: 1 - Critical",
  "prevalence": "선택 - 예: 1 - All users",
  "repro_rate": "선택 - 예: 1 - 100% reproducible",
  "branch": "선택 - 예: release/1.2.3 또는 a,b,c(쉼표구분)",
  "build": "선택 - 예: 12345 또는 a,b,c(쉼표구분)",
  "fixversion": "선택 - 예: 1.2.3 또는 a,b,c(쉼표구분)",
  "component": "선택 - 예: UI,Matchmaking (쉼표구분)",
  "reviewer": "선택 - Reviewer(커스텀 필드)",
  "parent": "선택 - 부모 이슈 키(예: P2-1234)",
  "linkedIssues": "현재 미사용(향후 issueLink 구현용 입력)",
  "issue": "현재 미사용(향후 issueLink 구현용 입력)",
  "steps": "선택 - Steps to Reproduce(커스텀 필드, 문서형식으로 변환)",
  "description": "선택 - Description(문서형식으로 변환)"
}
```

중요:

- **서버에서 강제 검증하는 필수값은 `summary`만**입니다.  
  다만 실제 JIRA 프로젝트 설정에 따라 `branch/build/steps` 같은 커스텀 필드가 필수일 수 있으니, 운영 환경에서는 프론트/서버 검증을 추가하는 것을 권장합니다.
- UI에는 `assignee` 입력이 있지만, `getFormData()`에 포함되지 않아 **서버로 전달되지 않습니다.**

---

## 서버 → JIRA Payload 변환 규칙 (핵심)

변환 위치: `api/jira_api.py`의 `JiraAPIClient._convert_to_jira_format(issue_data)`

### 기본 필드

- **Project Key**: `api/jira_config.json`의 `project_key`
- **Issue Type**: `api/jira_config.json`의 `issue_type`
- **Summary**: `issue_data.summary`

### Description / Steps (Atlassian Document Format)

- `description`, `steps`는 문자열을 그대로 보내지 않고, **Atlassian Document Format(doc/version/content)** 으로 감싸서 전송합니다.

### Labels

- 입력: `label = "a,b,c"` (쉼표구분 문자열)
- 변환: `fields.labels = ["a", "b", "c"]`

### Components (요청하신 “컴포넌트 연결”)

- 입력: `component = "UI,Matchmaking"` (쉼표구분 문자열)
- 변환: `fields.components = [{ "name": "UI" }, { "name": "Matchmaking" }]`
- 주의: JIRA 프로젝트에 **존재하는 컴포넌트 이름**이어야 하며, 아니면 JIRA에서 필드 에러로 거절합니다.

### Fix Versions

- 입력: `fixversion = "1.2.3,1.2.4"`
- 변환: `fields.fixVersions = [{ "name": "1.2.3" }, { "name": "1.2.4" }]`

### Assignee

- 이 앱은 **항상 `jira_config.json`의 `email` 사용자로 자동 할당**합니다. (프론트에서 assignee를 보내지 않음)
- 다른 앱에서 “원버튼 등록”을 만들 때, 정책에 따라:
  - (A) 자동 할당을 유지하거나
  - (B) 요청 바디에 assignee를 넣고 `_convert_to_jira_format()`을 수정해 반영
  중 하나를 선택하면 됩니다.

### Custom Fields (jira_config.json 기반)

`api/jira_config.json`의 `custom_fields` 매핑을 사용합니다.

- **team**: `fields[teamFieldId] = { "value": team }`
- **reviewer**: `fields[reviewerFieldId] = { "name": reviewer }`
- **branch/build**: 문자열이면 쉼표로 분리해 **배열로 전송**
  - 예: `"a,b"` → `["a","b"]`
- **severity/prevalence/repro_rate**: Select 값 매핑 후 `{"value": ...}`로 전송

---

## Select 값(Severity/Prevalence/Repro Rate) 매핑 규칙

문제 상황(실무에서 자주 발생):

- 프론트 드롭다운 값이 `"1 - Critical"` 같은 형식인데,
- JIRA는 실제 옵션 텍스트/순서가 다르면 거절(필드 에러)합니다.

이 앱은 `api/field_options_config.json`을 통해 **“드롭다운 순서 기반” 매핑**을 합니다.

- 파일: `api/field_options_config.json`
- 규칙: 드롭다운 1번째 선택 → `options[0]`, 2번째 → `options[1]` …

다른 앱에서 원버튼 구현 시 권장:

- (권장) JIRA에서 옵션을 조회해 로컬 매핑을 생성/갱신한 뒤 전송
- (최소) 이 앱처럼 `field_options_config.json`을 프로젝트별로 유지

---

## 서버 응답 규격(성공/실패)

### 성공 응답 예시

```json
{
  "success": true,
  "issue_key": "P2-1234",
  "issue_url": "https://<your-domain>.atlassian.net/browse/P2-1234",
  "message": "JIRA 이슈가 성공적으로 생성되었습니다."
}
```

### 실패 응답 예시(필드별 에러 포함 가능)

```json
{
  "success": false,
  "error": "이슈 생성 실패 (400)",
  "details": "• Components (components): Field 'components' cannot be set. ...",
  "field_errors": {
    "components": {
      "field_id": "components",
      "message": "Field 'components' cannot be set.",
      "value": [{"name": "NotExistComponent"}]
    }
  },
  "raw_error": "{...JIRA raw response text...}"
}
```

포인트:

- 백엔드는 JIRA 에러 응답의 `errors`를 파싱해서 **필드별 에러를 구조화**해 내려줍니다.
- 프론트는 이를 사용자 메시지로 보기 좋게 재구성해 표시합니다.

---

## “Linked Issues(이슈 링크)” 관련 현재 상태

프론트 입력 필드(`linkedIssues`, `issue`)는 존재하지만,
`JiraAPIClient._convert_to_jira_format()`에서는 값을 읽기만 하고 **실제 issueLink 생성은 구현되어 있지 않습니다.**

다른 앱에서 이슈 링크까지 원버튼으로 처리하려면:

- 1) 이슈 생성(`POST /rest/api/3/issue`) 후 issueKey 확보
- 2) 별도 API로 링크 생성(예: `POST /rest/api/3/issueLink`)
로 2단계로 구현하는 것이 일반적입니다.

---

## 다른 앱에서 그대로 참고하는 “원버튼 호출” 예시

### (옵션 A) 이 Flask 서버를 그대로 재사용하는 경우

```bash
curl -X POST "http://<this-server-host>:5000/api/issues" ^
  -H "Content-Type: application/json" ^
  -d "{\"summary\":\"[OneButton] 크래시\",\"priority\":\"High\",\"component\":\"UI\",\"description\":\"재현됨\",\"steps\":\"1) ...\"}"
```

### (옵션 B) 다른 앱이 직접 JIRA REST API를 호출하는 경우

이 프로젝트 기준으로는 `JiraAPIClient._convert_to_jira_format()`이 “정답 payload” 역할을 하므로,
다른 앱에서도 동일한 필드 매핑/문서 포맷(Atlassian Document Format)을 구현하면 됩니다.

---

## 설정 파일(꼭 확인)

- `api/jira_config.json`
  - `base_url`, `email`, `api_token`, `project_key`, `issue_type`
  - `custom_fields`: 프로젝트별 커스텀필드 ID 매핑

보안 권장:

- `api_token`은 **Git에 커밋하지 않는 것**을 강력히 권장합니다(환경변수/비공개 설정 파일 권장).


