#!/usr/bin/env python
"""
QuickRail 테스트 프로젝트 시딩 스크립트

대상 프로젝트: "Quickrail Phase1"

요구사항:
- 프로젝트 내 기존 케이스를 "전부 삭제" 후 다시 생성
- 섹션 제목에서 'Phase 1' 문구 제거
- 현재까지 구현된 QuickRail의 기능(Phase1 포함 + 기존 기능 전체)을 커버하는 테스트 케이스 생성
- 케이스 타이틀에 [TC ...] 같은 접두사를 붙이지 않음

주의:
- Windows 콘솔(cp949) 환경에서 인코딩 오류를 피하기 위해 이모지 사용 금지
- production 설정으로 실행(SQLAlchemy echo 로그 최소화)
"""

from __future__ import annotations

from app import create_app, db
from app.models import (
    User,
    Project,
    Section,
    Case,
    Tag,
    CaseTag,
    CaseTranslation,
    Run,
    RunTemplate,
    TranslationUsage,
)


PROJECT_NAME = "Quickrail Phase1"
PROJECT_DESCRIPTION = (
    "QuickRail 전체 기능 검증용 테스트 프로젝트 "
    "(Cases/Sections/Tags/Import/Translation/Prompts/Runs/Results/Comments/BugLinks/Attachments/CSV/Summary/Jira/Presence)"
)


SECTIONS = [
    "인증/권한",
    "프로젝트/대시보드",
    "섹션(트리)",
    "케이스 관리",
    "태그/필터/정렬",
    "케이스 Import/Export",
    "번역(케이스)",
    "설정(/settings)",
    "고급 설정(/advanced-settings)",
    "런 관리",
    "런 실행(결과)",
    "코멘트/버그 링크",
    "첨부파일",
    "CSV Export(런)",
    "AI 요약(완료 런)",
    "Jira 원버튼",
    "런 템플릿",
    "Presence(온라인)",
]


TEST_CASES = [
    # 인증/권한
    {
        "section": "인증/권한",
        "title": "로그인 성공/실패 기본 동작",
        "steps": "1) 로그인 페이지 이동\n2) 잘못된 계정/비밀번호로 로그인 시도\n3) 올바른 계정/비밀번호로 로그인 시도",
        "expected_result": "실패 시 로그인되지 않고 오류 안내가 표시된다.\n성공 시 프로젝트 목록으로 이동한다.",
        "priority": "Critical",
        "tags": ["auth"],
    },
    {
        "section": "인증/권한",
        "title": "로그아웃 상태에서 보호된 페이지 접근 제한",
        "steps": "1) 로그아웃 상태에서 /projects 또는 /p/<id>/cases 접근\n2) 로그인 후 재접근",
        "expected_result": "로그아웃 상태에서는 로그인 페이지로 리다이렉트된다.\n로그인 후 정상 접근된다.",
        "priority": "High",
        "tags": ["auth"],
    },
    {
        "section": "인증/권한",
        "title": "관리자 전용 기능 접근 제한(고급 설정/API키)",
        "steps": "1) 일반 계정으로 /advanced-settings 접근\n2) admin/super admin 계정으로 접근",
        "expected_result": "일반 계정은 403(또는 접근 불가) 처리된다.\n관리자는 접근 가능하다.",
        "priority": "High",
        "tags": ["auth", "role"],
    },

    # 프로젝트/대시보드
    {
        "section": "프로젝트/대시보드",
        "title": "프로젝트 목록 표시 및 프로젝트 진입",
        "steps": "1) /projects 페이지에서 프로젝트 목록 확인\n2) 프로젝트 클릭하여 진입",
        "expected_result": "프로젝트 목록이 표시되고, 클릭 시 해당 프로젝트로 이동한다.",
        "priority": "Medium",
        "tags": ["project"],
    },
    {
        "section": "프로젝트/대시보드",
        "title": "프로젝트 대시보드에서 최근 런 표시",
        "steps": "1) 프로젝트 대시보드 이동\n2) 최근 런/통계 영역 확인",
        "expected_result": "프로젝트의 최근 런 정보가 표시된다.",
        "priority": "Low",
        "tags": ["dashboard"],
    },

    # 섹션(트리)
    {
        "section": "섹션(트리)",
        "title": "섹션 생성 및 하위 섹션 생성",
        "steps": "1) 케이스 페이지에서 상위 섹션 생성\n2) 상위 섹션 아래 하위 섹션 생성\n3) 트리 표시 확인",
        "expected_result": "트리에 부모-자식 구조가 올바르게 표시된다.",
        "priority": "High",
        "tags": ["section"],
    },
    {
        "section": "섹션(트리)",
        "title": "섹션 경로(Parent > Child) 표시 확인",
        "steps": "1) 2~3단계 깊이의 섹션 구성\n2) 해당 섹션의 케이스를 Export 또는 UI에서 경로 확인",
        "expected_result": "섹션 경로가 Parent > Child > Grandchild 형식으로 올바르게 표시된다.",
        "priority": "Medium",
        "tags": ["section"],
    },

    # 케이스 관리
    {
        "section": "케이스 관리",
        "title": "케이스 생성/수정 기본 동작",
        "steps": "1) 케이스 생성(제목/스텝/예상결과/우선순위)\n2) 생성된 케이스 내용 수정\n3) 저장/반영 확인",
        "expected_result": "생성/수정 내용이 저장되고 목록/상세에 반영된다.",
        "priority": "Critical",
        "tags": ["case"],
    },
    {
        "section": "케이스 관리",
        "title": "케이스 아카이브(비활성) 처리 후 목록 제외",
        "steps": "1) 케이스를 아카이브 처리\n2) 기본 목록에서 제외되는지 확인",
        "expected_result": "아카이브된 케이스는 기본 목록에서 보이지 않는다.",
        "priority": "High",
        "tags": ["case"],
    },
    {
        "section": "케이스 관리",
        "title": "케이스 버전 증가(제목/스텝/예상결과 변경)",
        "steps": "1) 케이스 version 확인\n2) 제목 변경 후 version 확인\n3) 스텝 변경 후 version 확인\n4) 예상결과 변경 후 version 확인",
        "expected_result": "각 변경 시 version이 1씩 증가한다.",
        "priority": "High",
        "tags": ["case", "version"],
    },

    # 태그/필터/정렬
    {
        "section": "태그/필터/정렬",
        "title": "태그 추가/제거 및 태그 필터 동작",
        "steps": "1) 케이스에 태그 추가\n2) 태그로 필터링\n3) 태그 제거 후 필터 결과 갱신 확인",
        "expected_result": "태그 필터가 정확히 동작하고 변경 사항이 반영된다.",
        "priority": "High",
        "tags": ["tag", "filter"],
    },
    {
        "section": "태그/필터/정렬",
        "title": "키워드 검색(q) 및 정렬 옵션 동작",
        "steps": "1) 제목/스텝/예상결과 키워드로 검색\n2) 정렬 옵션 변경(최근/제목/우선순위 등)",
        "expected_result": "검색/정렬 결과가 기대대로 동작한다.",
        "priority": "High",
        "tags": ["filter"],
    },

    # 케이스 Import/Export
    {
        "section": "케이스 Import/Export",
        "title": "케이스 Export(CSV) 및 Excel 한글 인코딩 확인",
        "steps": "1) 섹션 케이스를 CSV로 Export\n2) Excel로 열기\n3) 한글 깨짐 여부 확인",
        "expected_result": "CSV가 다운로드되고 Excel에서 한글이 정상 표시된다.",
        "priority": "High",
        "tags": ["export"],
    },
    {
        "section": "케이스 Import/Export",
        "title": "케이스 Import(Preview -> Confirm) 기본 동작",
        "steps": "1) 케이스 Import에서 파일 업로드\n2) Preview에서 컬럼/매핑 확인\n3) Confirm으로 생성",
        "expected_result": "Preview가 표시되고 Confirm 후 케이스가 생성된다.",
        "priority": "High",
        "tags": ["import"],
    },
    {
        "section": "케이스 Import/Export",
        "title": "케이스 Import: 섹션 전체(a > b > c) 컬럼 매핑으로 depth 1~4 자동 분해",
        "steps": "1) Import Step2에서 '섹션 전체' 컬럼을 선택\n2) 샘플 프리뷰에서 a > b > c 형태 분해 확인\n3) Preview/Confirm 진행\n4) 생성된 섹션 트리/케이스 위치 확인",
        "expected_result": "'섹션 전체' 값이 '>' 기준으로 분해되어 depth 1~4에 적용된다.\n생성된 케이스가 올바른 섹션 경로에 배치된다.",
        "priority": "High",
        "tags": ["import", "section"],
    },
    {
        "section": "케이스 Import/Export",
        "title": "케이스 Import: 최상위 섹션 depth에 따른 섹션 depth 매핑 비활성화 동작",
        "steps": "1) Import Step2에서 최상위 섹션을 depth=2 위치로 선택\n2) 섹션 depth 3~4 매핑 드롭다운이 비활성화되는지 확인\n3) 최상위 섹션 변경/해제 시 동적 갱신 확인",
        "expected_result": "최상위 섹션 depth에 따라 depth 매핑 입력이 동적으로 제한된다.\n비활성화된 depth의 값은 입력/적용되지 않는다.",
        "priority": "Medium",
        "tags": ["import", "section"],
    },
    {
        "section": "케이스 Import/Export",
        "title": "케이스 Import: Jira Links/Media URLs 컬럼 매핑 및 저장",
        "steps": "1) Import 파일에 Jira Links, Media URLs 컬럼 포함\n2) Step2에서 Jira Links/Media 매핑\n3) Confirm 후 케이스 상세에서 Jira 링크/미디어 확인",
        "expected_result": "케이스별 Jira 링크(복수)가 저장되고, Media URLs는 다운로드되어 케이스 미디어로 저장된다.",
        "priority": "High",
        "tags": ["import", "jira", "media"],
    },

    # 번역(케이스)
    {
        "section": "번역(케이스)",
        "title": "단건 번역 수행 및 번역 결과 저장",
        "steps": "1) 한국어 케이스 준비\n2) 영어 번역 수행\n3) 번역 결과(제목/스텝/예상결과) 저장 확인",
        "expected_result": "번역 결과가 저장되고 화면에 표시된다.",
        "priority": "High",
        "tags": ["translation"],
    },
    {
        "section": "번역(케이스)",
        "title": "일괄 번역(batch) 수행",
        "steps": "1) 여러 케이스 선택\n2) 일괄 번역 실행\n3) 번역 결과 반영 확인",
        "expected_result": "선택한 케이스들이 일괄 번역되어 반영된다.",
        "priority": "Medium",
        "tags": ["translation"],
    },
    {
        "section": "번역(케이스)",
        "title": "번역 사용량/비용 기록 생성(TranslationUsage)",
        "steps": "1) 번역 실행\n2) 사용량/비용 기록이 생성되는지 확인",
        "expected_result": "번역 실행 후 사용량/비용 기록이 누적된다.",
        "priority": "Low",
        "tags": ["translation", "usage"],
    },

    # 설정(/settings)
    {
        "section": "설정(/settings)",
        "title": "번역 프롬프트 CRUD 및 활성화",
        "steps": "1) 번역 프롬프트 생성\n2) 편집\n3) 활성화\n4) 비활성 프롬프트 삭제",
        "expected_result": "번역 프롬프트의 생성/수정/활성화/삭제가 동작한다.",
        "priority": "High",
        "tags": ["settings", "prompt"],
    },
    {
        "section": "설정(/settings)",
        "title": "요약 프롬프트 CRUD 및 활성화",
        "steps": "1) 요약 프롬프트 생성\n2) 편집\n3) 활성화\n4) 비활성 프롬프트 삭제",
        "expected_result": "요약 프롬프트의 생성/수정/활성화/삭제가 동작한다.",
        "priority": "High",
        "tags": ["settings", "summary"],
    },
    {
        "section": "설정(/settings)",
        "title": "Jira 원버튼 설정 로드/저장",
        "steps": "1) 설정 페이지에서 Jira 원버튼 탭 진입\n2) 설정값 로드 확인\n3) (관리자) 설정 저장",
        "expected_result": "Jira 설정값이 로드되고 관리자 권한에서 저장된다.",
        "priority": "High",
        "tags": ["settings", "jira"],
    },

    # 고급 설정(/advanced-settings)
    {
        "section": "고급 설정(/advanced-settings)",
        "title": "OpenAI API 키 추가/활성화/삭제 기본 동작",
        "steps": "1) 고급 설정에서 API 키 추가\n2) 활성화\n3) 비활성 키 삭제",
        "expected_result": "API 키 관리 기능이 정상 동작한다(권한 포함).",
        "priority": "High",
        "tags": ["advanced", "apikey"],
    },

    # 런 관리
    {
        "section": "런 관리",
        "title": "런 생성(이름/타입/빌드 라벨/케이스 선택)",
        "steps": "1) 런 목록에서 새 런 생성\n2) 이름/타입/빌드 라벨 입력\n3) 케이스 선택 후 생성",
        "expected_result": "런이 생성되고 목록에 표시되며 빌드 라벨이 표시된다.",
        "priority": "Critical",
        "tags": ["run"],
    },
    {
        "section": "런 관리",
        "title": "런 닫기(완료) 후 완료 런 목록 반영",
        "steps": "1) 진행 중 런에서 닫기 실행\n2) 완료 런 영역에 표시 확인",
        "expected_result": "런이 완료 상태로 전환되고 완료 런 목록에 표시된다.",
        "priority": "High",
        "tags": ["run", "closed"],
    },
    {
        "section": "런 관리",
        "title": "런 리셋(결과 초기화) 동작",
        "steps": "1) 일부 케이스에 결과 기록\n2) 리셋 실행\n3) 결과/통계/사이드바 초기화 확인",
        "expected_result": "결과가 초기화되어 미실행 상태로 돌아간다.",
        "priority": "High",
        "tags": ["run"],
    },

    # 런 실행(결과)
    {
        "section": "런 실행(결과)",
        "title": "결과 기록 상태(Pass/Fail/Blocked/Retest/NA) 및 배지/통계 반영",
        "steps": "1) 런 실행에서 케이스 선택\n2) 상태 버튼으로 결과 기록\n3) 사이드바 배지/통계 갱신 확인",
        "expected_result": "결과가 저장되고 배지/통계가 즉시 갱신된다.",
        "priority": "Critical",
        "tags": ["run", "result"],
    },
    {
        "section": "런 실행(결과)",
        "title": "단축키로 결과 기록 및 케이스 이동",
        "steps": "1) 단축키 1~5로 결과 기록\n2) j/k로 이동\n3) n/p로 미실행 이동",
        "expected_result": "단축키가 정상 동작한다.",
        "priority": "Medium",
        "tags": ["run", "hotkey"],
    },

    # 코멘트/버그 링크
    {
        "section": "코멘트/버그 링크",
        "title": "코멘트 추가/삭제 및 케이스별 코멘트 조회",
        "steps": "1) 코멘트 추가\n2) 목록 최신순 확인\n3) 작성자만 삭제 가능 확인",
        "expected_result": "코멘트가 저장/조회/삭제된다.",
        "priority": "High",
        "tags": ["comment"],
    },
    {
        "section": "코멘트/버그 링크",
        "title": "완료된 런에서 코멘트 프리뷰가 사이드바에 표시됨",
        "steps": "1) 결과 없이 코멘트만 저장\n2) 런 완료\n3) 완료 런에서 사이드바 프리뷰 확인",
        "expected_result": "완료 런에서도 코멘트 프리뷰가 사이드바에 표시된다.",
        "priority": "Critical",
        "tags": ["comment", "closed"],
    },
    {
        "section": "코멘트/버그 링크",
        "title": "버그 링크 추가/삭제 및 결과 저장 반영",
        "steps": "1) 버그 링크 추가\n2) 저장 후 목록 표시 확인\n3) 삭제 후 반영 확인",
        "expected_result": "버그 링크가 저장되고 목록이 갱신된다.",
        "priority": "High",
        "tags": ["buglinks"],
    },

    # 첨부파일
    {
        "section": "첨부파일",
        "title": "런 첨부파일 업로드(파일 선택/클립보드) 및 목록 표시",
        "steps": "1) 런 실행에서 첨부파일 선택(이미지/동영상)\n2) 업로드 후 목록이 한 줄(row)로 표시되는지 확인\n3) 클립보드 붙여넣기로도 업로드 확인",
        "expected_result": "업로드가 성공하고 첨부 목록에 한 줄씩 표시된다.\n클립보드 붙여넣기도 정상 업로드된다.",
        "priority": "High",
        "tags": ["attachment"],
    },
    {
        "section": "첨부파일",
        "title": "첨부파일 클릭 시 브라우저에서 바로 보기(inline) + 다운로드 버튼 분리",
        "steps": "1) 첨부 목록에서 파일명 링크 클릭\n2) 이미지/영상은 모달 또는 새 탭에서 바로 표시되는지 확인\n3) 다운로드 버튼 클릭 시 다운로드되는지 확인",
        "expected_result": "기본 동작은 inline 보기이며, 다운로드는 별도 버튼으로만 수행된다.",
        "priority": "High",
        "tags": ["attachment"],
    },
    {
        "section": "첨부파일",
        "title": "첨부파일 삭제 버튼 동작(진행 중 런) 및 완료 런 삭제 제한",
        "steps": "1) 진행 중 런에서 첨부 업로드\n2) 삭제 버튼(휴지통)으로 삭제\n3) 런 완료 후 동일 첨부 삭제 시도",
        "expected_result": "진행 중 런에서는 삭제가 가능하다.\n완료된 런에서는 첨부 삭제가 제한된다.",
        "priority": "High",
        "tags": ["attachment", "closed"],
    },

    # 런 실행(결과) 보강
    {
        "section": "런 실행(결과)",
        "title": "런 우측 패널: 케이스 Jira/미디어와 런 버그링크/첨부가 단일 섹션으로 통합 표시",
        "steps": "1) 런 실행 우측 상세 패널 확인\n2) Jira/버그 링크 영역에 케이스 링크 + 런 버그 링크가 함께 표시되는지 확인\n3) 첨부 영역에 케이스 미디어 + 런 첨부가 함께 표시되는지 확인",
        "expected_result": "중복 영역 없이 Jira/버그 링크는 1개 영역, 첨부는 1개 영역으로 통합 표시된다.",
        "priority": "Medium",
        "tags": ["run", "ui"],
    },

    # 케이스 관리 보강(케이스 Jira/미디어)
    {
        "section": "케이스 관리",
        "title": "케이스 상세 모달에서 케이스 Jira 링크 추가/조회",
        "steps": "1) cases 페이지에서 케이스 상세 모달(F4) 열기\n2) Jira 링크 추가\n3) 새로고침/재오픈 후에도 링크 유지 확인",
        "expected_result": "케이스별 Jira 링크가 저장되고 재조회 시에도 표시된다.",
        "priority": "High",
        "tags": ["case", "jira"],
    },
    {
        "section": "케이스 관리",
        "title": "케이스 상세 모달에서 미디어 업로드/조회/삭제",
        "steps": "1) cases 상세 모달에서 이미지/영상 업로드\n2) 링크 클릭 시 inline 보기 확인\n3) 삭제 버튼으로 삭제",
        "expected_result": "케이스 미디어가 저장되고 inline 보기 가능하며 삭제도 동작한다.",
        "priority": "High",
        "tags": ["case", "media"],
    },

    # CSV Export(런)
    {
        "section": "CSV Export(런)",
        "title": "런 CSV Export 다운로드 및 컬럼 구조 확인",
        "steps": "1) 런 실행에서 CSV Export\n2) 헤더/컬럼 확인",
        "expected_result": "CSV가 다운로드되고 런/케이스/결과/코멘트/버그링크 컬럼이 포함된다.",
        "priority": "Critical",
        "tags": ["csv"],
    },

    # AI 요약(완료 런)
    {
        "section": "AI 요약(완료 런)",
        "title": "완료된 런에서 요약 프롬프트 로드 및 요약 생성",
        "steps": "1) 런 완료\n2) AI 요약 영역에서 프롬프트 선택\n3) 요약 생성",
        "expected_result": "요약이 생성되어 표시되고 복사/새창 기능이 동작한다.",
        "priority": "High",
        "tags": ["summary"],
    },

    # Jira 원버튼
    {
        "section": "Jira 원버튼",
        "title": "Jira 비활성 상태에서 원버튼 이슈 생성 실패 안내",
        "steps": "1) Jira 원버튼 enabled 끔\n2) 런 실행에서 이슈 생성 시도",
        "expected_result": "비활성화 안내로 실패 처리된다.",
        "priority": "High",
        "tags": ["jira"],
    },
    {
        "section": "Jira 원버튼",
        "title": "Jira 활성+필수값 설정 후 원버튼 이슈 생성",
        "steps": "1) Jira enabled 켬\n2) base_url/email/api_token/project_key/issue_type 설정\n3) 런 실행에서 이슈 생성",
        "expected_result": "이슈가 생성되고 URL이 버그 링크 목록에 자동 추가된다.",
        "priority": "Critical",
        "tags": ["jira"],
    },

    # 런 템플릿
    {
        "section": "런 템플릿",
        "title": "런 템플릿 생성 및 템플릿으로 런 생성",
        "steps": "1) 런 템플릿 생성\n2) 템플릿으로 런 생성",
        "expected_result": "템플릿 기반 런이 생성된다.",
        "priority": "Medium",
        "tags": ["template"],
    },

    # Presence(온라인)
    {
        "section": "Presence(온라인)",
        "title": "온라인 사용자 목록 및 heartbeat 동작",
        "steps": "1) 2개 계정으로 로그인(2 브라우저)\n2) 온라인 목록 확인\n3) TTL 경과 후 오프라인 확인",
        "expected_result": "온라인 목록이 갱신되고 TTL에 따라 오프라인 처리된다.",
        "priority": "Low",
        "tags": ["presence"],
    },
]


def _pick_actor_user() -> User:
    admin = User.query.filter_by(email="admin@quickrail.com").first()
    if admin:
        return admin
    admin2 = User.query.filter(User.role.in_(["Super Admin", "admin"])).first()
    if admin2:
        return admin2
    any_user = User.query.first()
    if not any_user:
        raise RuntimeError("사용자를 찾을 수 없습니다. 먼저 사용자/DB 초기화를 진행하세요.")
    return any_user


def _wipe_project_data(project_id: int) -> None:
    """프로젝트 내 테스트 데이터 정리.

    주의: 단순 bulk delete는 ORM cascade를 무시할 수 있어,
    Run/RunTemplate 등은 개별 delete로 처리한다.
    """
    print("[INFO] 기존 데이터 정리 시작...")

    # 1) 런 템플릿 삭제
    templates = RunTemplate.query.filter_by(project_id=project_id).all()
    for t in templates:
        db.session.delete(t)
    db.session.flush()

    # 2) 런 삭제 (Run -> run_cases/results cascade)
    runs = Run.query.filter_by(project_id=project_id).all()
    for r in runs:
        db.session.delete(r)
    db.session.flush()

    # 3) 케이스 목록 확보 (ORM 객체 로드 없이 ID만)
    case_ids = [cid for (cid,) in db.session.query(Case.id).filter(Case.project_id == project_id).all()]

    if case_ids:
        # TranslationUsage는 case_id FK가 nullable이지만 ondelete가 없을 수 있어 NULL 처리
        TranslationUsage.query.filter(TranslationUsage.case_id.in_(case_ids)).update(
            {TranslationUsage.case_id: None}, synchronize_session=False
        )
        db.session.flush()

        # 번역/태그 연결 제거 (bulk delete)
        CaseTranslation.query.filter(CaseTranslation.case_id.in_(case_ids)).delete(synchronize_session=False)
        CaseTag.query.filter(CaseTag.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.session.flush()

        # 케이스 삭제 (bulk delete) - association rowcount mismatch(StaleDataError) 방지
        Case.query.filter(Case.id.in_(case_ids)).delete(synchronize_session=False)
        db.session.flush()

    # 4) 섹션 삭제(부모->자식 self FK 고려: depth 역순)
    sections = Section.query.filter_by(project_id=project_id).all()
    if sections:
        section_map = {s.id: s for s in sections}
        depth_cache: dict[int, int] = {}

        def depth(s: Section) -> int:
            if s.id in depth_cache:
                return depth_cache[s.id]
            d = 0
            cur = s
            while cur.parent_id:
                d += 1
                parent = section_map.get(cur.parent_id)
                if not parent:
                    break
                cur = parent
            depth_cache[s.id] = d
            return d

        for s in sorted(sections, key=depth, reverse=True):
            db.session.delete(s)
        db.session.flush()

    # 5) 태그 삭제(프로젝트 스코프)
    Tag.query.filter_by(project_id=project_id).delete(synchronize_session=False)
    db.session.flush()

    db.session.commit()
    print("[INFO] 기존 데이터 정리 완료")


def _ensure_sections(project_id: int) -> dict[str, int]:
    """섹션 생성 및 id 맵 반환"""
    section_id_by_name: dict[str, int] = {}
    for name in SECTIONS:
        s = Section(project_id=project_id, name=name, parent_id=None)
        db.session.add(s)
        db.session.flush()
        section_id_by_name[name] = s.id
        print(f"[OK] 섹션 생성: {name} (ID: {s.id})")
    db.session.commit()
    return section_id_by_name


def _create_cases(project_id: int, actor_id: int, section_id_by_name: dict[str, int]) -> int:
    created = 0
    for tc in TEST_CASES:
        section_name = tc["section"]
        section_id = section_id_by_name.get(section_name)
        if not section_id:
            print(f"[ERROR] 섹션을 찾을 수 없음: {section_name}")
            continue

        title = tc["title"]
        existing = Case.query.filter_by(project_id=project_id, title=title).first()
        if existing:
            continue

        case = Case(
            project_id=project_id,
            section_id=section_id,
            title=title,
            steps=tc.get("steps") or "",
            expected_result=tc.get("expected_result") or "",
            priority=tc.get("priority") or "Medium",
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.session.add(case)
        db.session.flush()

        for tag_name in tc.get("tags") or []:
            tag_key = str(tag_name).strip().lower()
            if not tag_key:
                continue
            tag = Tag.query.filter_by(project_id=project_id, name=tag_key).first()
            if not tag:
                tag = Tag(project_id=project_id, name=tag_key)
                db.session.add(tag)
                db.session.flush()
            db.session.add(CaseTag(case_id=case.id, tag_id=tag.id))

        created += 1
        print(f"[OK] 케이스 생성: {title} (ID: {case.id})")

    db.session.commit()
    return created


def main() -> None:
    app = create_app("production")
    with app.app_context():
        actor = _pick_actor_user()

        project = Project.query.filter_by(name=PROJECT_NAME).first()
        if not project:
            project = Project(name=PROJECT_NAME, description=PROJECT_DESCRIPTION)
            db.session.add(project)
            db.session.commit()
            print(f"[OK] 프로젝트 생성: {project.name} (ID: {project.id})")
        else:
            # 설명 갱신(선택)
            project.description = PROJECT_DESCRIPTION
            db.session.commit()
            print(f"[INFO] 기존 프로젝트 사용: {project.name} (ID: {project.id})")

        project_id = project.id

        # wipe + recreate
        _wipe_project_data(project_id)
        section_id_by_name = _ensure_sections(project_id)
        created_count = _create_cases(project_id, actor.id, section_id_by_name)

        print("\n" + "=" * 60)
        print(f"[DONE] 완료! 신규 {created_count}개의 테스트 케이스가 생성되었습니다.")
        print(f"프로젝트에서 확인: http://127.0.0.1:5000/p/{project_id}/cases")
        print("=" * 60)


if __name__ == "__main__":
    main()


