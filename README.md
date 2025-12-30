# QuickRail

TestRail 유사 기능을 제공하는 경량 테스트 관리 웹 애플리케이션입니다.
사용자 중심의 UX로 클릭/이동/입력 부담을 최소화했습니다.

## 주요 기능

### Phase 1 (MVP) ✅ 완료
- ✅ 사용자 인증 (로그인/회원가입)
- ✅ 프로젝트 관리
- ✅ 섹션 트리 구조
- ✅ 테스트 케이스 CRUD
- ✅ 태그 및 검색/필터
- ✅ 테스트 런 생성 및 관리
- ✅ 런 실행 (키보드 단축키 지원)
- ✅ 기본 리포트 (진행률/Pass rate)

### Phase 2 (편의성 핵심) ✅ 완료
- ✅ 런 템플릿 (저장된 필터/셋)
- ✅ 키보드 핫키 고도화 (10+ 단축키)
- ✅ 케이스 중복 감지 (제목 기반 유사도)
- ✅ 운영 대시보드 (실패 Top, 오래된 케이스, Flaky 케이스)
- ✅ 섹션 드래그앤드롭 (계층 구조 변경)
- ✅ 런 생성 시 케이스 선택 모달

### 핵심 UX 특징
- **2-pane 레이아웃**: 좌측 섹션 트리, 우측 케이스 리스트
- **Quick Add**: 제목만 입력하여 케이스 즉시 생성
- **드래그앤드롭**: 섹션 순서 및 계층 구조 변경
- **중복 감지**: 케이스 작성 시 유사한 제목 자동 감지
- **키보드 중심 실행**: 10+ 핫키로 빠른 테스트 실행
- **런 템플릿**: 자주 쓰는 케이스 셋을 템플릿으로 저장
- **실시간 통계**: 런 진행률과 Pass rate 실시간 업데이트
- **운영 인사이트**: 자주 실패하는 케이스, 오래된 케이스, 불안정한 케이스 분석

## 기술 스택

- **Backend**: Flask 3.0
- **Database**: SQLite (개발) / PostgreSQL (운영 권장)
- **ORM**: SQLAlchemy
- **Authentication**: Flask-Login
- **Migration**: Alembic (Flask-Migrate)
- **Frontend**: Jinja2 템플릿 + HTMX
- **CSS**: Custom (경량화)

## 설치 및 실행

### 1. 환경 설정

```bash
# Python 가상환경 생성
python -m venv venv

# 가상환경 활성화 (Windows)
venv\Scripts\activate

# 가상환경 활성화 (Linux/Mac)
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env` 파일 생성 (`.env.example` 참고):

```
FLASK_APP=run.py
FLASK_ENV=development
SECRET_KEY=your-secret-key-change-in-production
DATABASE_URL=sqlite:///quickrail.db
```

### 3. 데이터베이스 초기화

```bash
# 데이터베이스 및 샘플 데이터 생성
python run.py init-db
```

샘플 사용자:
- **Admin**: admin@quickrail.com / admin123
- **Author**: author@quickrail.com / author123
- **Runner**: runner@quickrail.com / runner123

### 4. 애플리케이션 실행

```bash
python run.py
```

브라우저에서 http://localhost:5000 접속

## 프로젝트 구조

```
QuickRail/
├── app/
│   ├── __init__.py          # Flask 앱 팩토리
│   ├── models.py            # 데이터 모델
│   ├── routes/              # 라우트 블루프린트
│   │   ├── auth.py          # 인증 라우트
│   │   ├── main.py          # 메인 페이지 라우트
│   │   └── api.py           # REST API
│   └── templates/           # Jinja2 템플릿
│       ├── base.html        # 기본 레이아웃
│       ├── auth/            # 인증 템플릿
│       └── main/            # 메인 템플릿
├── config.py                # 설정 파일
├── run.py                   # 실행 스크립트
├── requirements.txt         # Python 의존성
└── Design.md               # 상세 설계 문서
```

## 사용 방법

### 1. 프로젝트 생성
- 로그인 후 "새 프로젝트" 버튼 클릭
- 프로젝트 이름 및 설명 입력

### 2. 케이스 관리
- 프로젝트 > 케이스 메뉴 선택
- 좌측에서 섹션 생성/선택
- Quick Add로 케이스 빠르게 추가
- 필터/검색으로 케이스 찾기

### 3. 런 생성
- 프로젝트 > 런 메뉴 선택
- "새 런 생성" 클릭
- 포함할 케이스 ID 입력 (쉼표로 구분)

### 4. 런 실행
- 런 목록에서 런 클릭
- 키보드 단축키로 빠른 실행:
  - `1`: Pass
  - `2`: Fail (코멘트 필수)
  - `3`: Blocked
  - `4`: Retest
  - `5`: N/A
  - `n`: 다음 미실행 케이스
  - `p`: 이전 미실행 케이스
  - `j/k`: 다음/이전 케이스
  - `g`: 첫 케이스
  - `G`: 마지막 케이스
  - `c`: 코멘트 포커스
  - `r`: 통계 새로고침
  - `Esc`: 코멘트 닫기
  - `?`: 단축키 힌트 토글

### 5. 런 템플릿 사용
- 런 페이지에서 "템플릿" 버튼 클릭
- 자주 사용하는 케이스 조합을 템플릿으로 저장
- 템플릿에서 원클릭으로 런 생성

### 6. 리포트 확인
- 프로젝트 > 리포트 메뉴
- 최근 런들의 통계 확인
- **운영 인사이트**:
  - 🔥 자주 실패하는 케이스
  - ⏰ 오래된 케이스 (90일+)
  - ⚠️ 불안정한 케이스 (Flaky)

## API 엔드포인트

### 인증
- `POST /api/auth/login` - 로그인
- `GET /api/me` - 현재 사용자 정보

### 프로젝트
- `GET /api/projects` - 프로젝트 목록
- `POST /api/projects` - 프로젝트 생성
- `GET /api/projects/<id>` - 프로젝트 상세

### 케이스
- `GET /api/projects/<pid>/cases` - 케이스 목록 (필터 지원)
- `POST /api/projects/<pid>/cases` - 케이스 생성
- `GET /api/cases/<id>` - 케이스 상세
- `PATCH /api/cases/<id>` - 케이스 수정
- `POST /api/cases/<id>/archive` - 케이스 아카이브

### 런
- `GET /api/projects/<pid>/runs` - 런 목록
- `POST /api/projects/<pid>/runs` - 런 생성
- `GET /api/runs/<id>` - 런 상세
- `POST /api/runs/<id>/close` - 런 종료

### 결과
- `POST /api/runs/<rid>/results` - 결과 기록
- `GET /api/runs/<rid>/results` - 결과 목록

## 데이터 모델

### User
- 이메일, 이름, 비밀번호
- 역할: admin, author, runner

### Project
- 프로젝트 이름, 설명

### Section
- 트리 구조 (parent_id)
- 프로젝트별 그룹화

### Case
- 제목, 스텝, 기대결과
- 우선순위 (P0-P3)
- 태그, 오너
- 상태 (active/archived)

### Run
- 런 이름, 설명, 타입
- 생성자, 완료 여부

### Result
- 런-케이스 결과
- 상태: pass, fail, blocked, retest, na
- 코멘트, 첨부파일

## 개발 로드맵

### Phase 3 (확장 계획)
- REST API 개선
- Webhook
- Jira 연동
- Flaky 테스트 추적

## 라이선스

MIT License

## 기여

이슈 및 PR 환영합니다!

## 문의

프로젝트 관련 문의사항은 이슈로 등록해주세요.


