# QuickRail - 빠른 시작 가이드

## 1단계: 환경 준비

### Python 가상환경 생성 및 활성화

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 의존성 설치
```bash
pip install -r requirements.txt
```

## 2단계: 데이터베이스 초기화

```bash
# 데이터베이스 생성 및 샘플 데이터 추가
python run.py init-db
```

이 명령어는 다음을 수행합니다:
- SQLite 데이터베이스 생성 (`quickrail.db`)
- 모든 테이블 생성
- 샘플 사용자 3명 생성:
  - **Admin**: admin@quickrail.com / admin123
  - **Author**: author@quickrail.com / author123
  - **Runner**: runner@quickrail.com / runner123
- 샘플 프로젝트 1개 생성

## 3단계: 애플리케이션 실행

```bash
python run.py
```

브라우저에서 http://localhost:5000 접속

## 4단계: 사용해보기

### 1. 로그인
- admin@quickrail.com / admin123 으로 로그인

### 2. 프로젝트 생성 (또는 Sample Project 사용)
- "새 프로젝트" 버튼 클릭
- 프로젝트 이름 입력 (예: "테스트 프로젝트")

### 3. 섹션 생성
- 프로젝트 > 케이스 메뉴
- 좌측 섹션 트리에서 "+" 버튼 클릭
- 섹션 이름 입력 (예: "로그인 테스트")

### 4. 케이스 추가
- Quick Add 입력창에 케이스 제목 입력
- Enter 또는 "추가" 버튼 클릭
- 여러 케이스를 빠르게 추가

예시 케이스:
- "정상 로그인 테스트"
- "잘못된 비밀번호 로그인 테스트"
- "이메일 형식 검증 테스트"

### 5. 런 생성
- 프로젝트 > 런 메뉴
- "새 런 생성" 클릭
- 런 이름, 타입 선택
- 케이스 ID 입력 (예: 1,2,3)
- "생성" 클릭

### 6. 런 실행
- 생성된 런 클릭
- 키보드 단축키로 빠른 실행:
  - `1`: Pass
  - `2`: Fail
  - `3`: Blocked
  - `4`: Retest
  - `5`: N/A
  - `n`: 다음 미실행 케이스
  - `j/k`: 이전/다음
  - `?`: 단축키 힌트

### 7. 리포트 확인
- 프로젝트 > 리포트 메뉴
- Pass rate, 진행률 등 확인

## 트러블슈팅

### 포트가 이미 사용중일 때
```bash
python run.py
# 또는 다른 포트로 실행
flask run --port 5001
```

### 데이터베이스 초기화 (모든 데이터 삭제)
```bash
# quickrail.db 파일 삭제
rm quickrail.db  # Linux/Mac
del quickrail.db  # Windows

# 다시 초기화
python run.py init-db
```

### 의존성 문제
```bash
# 최신 pip 업그레이드
pip install --upgrade pip

# 의존성 재설치
pip install -r requirements.txt --force-reinstall
```

## 개발 모드 vs 운영 모드

### 개발 모드 (기본)
- DEBUG=True
- SQLite 사용
- 에러 트레이스 표시

### 운영 모드 설정
`.env` 파일 수정:
```
FLASK_ENV=production
SECRET_KEY=강력한-시크릿-키-생성
DATABASE_URL=postgresql://user:pass@localhost/quickrail
```

PostgreSQL 사용 시:
```bash
pip install psycopg2-binary
```

## 다음 단계

- Design.md 참고하여 고급 기능 이해
- API 문서 확인 (README.md)
- Phase 2 기능 확장 계획

## 문의 및 지원

문제가 발생하면 GitHub Issues에 등록해주세요!


