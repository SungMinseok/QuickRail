# QuickRail 번역 기능 설정 가이드

## 개요

QuickRail은 OpenAI GPT API를 사용하여 테스트 케이스를 자동으로 번역하는 기능을 제공합니다.
- **사전 번역 방식**: 케이스 생성/수정 시 자동으로 번역본을 생성하고 DB에 저장
- **지원 언어**: 한국어 ↔ 영어
- **번역 대상**: 케이스 제목, 테스트 스텝, 예상 결과

## 설정 방법

### 1. OpenAI API 키 발급

1. [OpenAI 플랫폼](https://platform.openai.com/)에 접속하여 계정 생성
2. API Keys 메뉴에서 새 API 키 생성
3. 생성된 API 키를 안전하게 보관

### 2. 환경 변수 설정

프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 다음 내용을 추가:

```bash
OPENAI_API_KEY=your-api-key-here
```

**중요**: `.env` 파일은 `.gitignore`에 포함되어 있어 Git에 커밋되지 않습니다.

### 3. 패키지 설치

```bash
# 가상환경 활성화
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 필요한 패키지 설치
pip install -r requirements.txt
```

### 4. 데이터베이스 마이그레이션

번역 기능을 위한 `case_translations` 테이블이 이미 생성되어 있습니다.
새로운 데이터베이스를 사용하는 경우:

```bash
flask db upgrade
```

## 사용 방법

### 케이스 리스트에서 언어 선택

1. 케이스 페이지 상단의 언어 선택 드롭다운 사용
2. 옵션:
   - **원본**: 작성된 원본 언어로 표시
   - **한국어**: 한국어로 번역하여 표시
   - **English**: 영어로 번역하여 표시

### 케이스 상세보기 모달에서 언어 전환

1. 케이스를 클릭하여 상세보기 모달 열기
2. 모달 헤더의 언어 버튼 클릭:
   - **원본** / **한국어** / **English**
3. 실시간으로 번역된 내용 확인

## 동작 방식

### 자동 번역

1. **케이스 생성 시**:
   - 제목의 언어를 자동 감지 (한국어/영어)
   - 반대 언어로 자동 번역하여 DB에 저장
   - 예: 한국어로 작성 → 영어 번역본 자동 생성

2. **케이스 수정 시**:
   - 제목, 스텝, 예상 결과 중 하나라도 변경되면
   - 기존 번역을 삭제하고 새로운 번역 생성

### 번역 캐싱

- 한 번 번역된 내용은 DB에 저장되어 재사용
- API 호출 횟수를 최소화하여 비용 절감
- 케이스 수정 시에만 재번역 수행

## 비용 관리

### GPT-3.5-turbo 사용

- 모델: `gpt-3.5-turbo`
- 예상 비용: 케이스당 약 $0.001 ~ $0.002
- 1,000개 케이스 번역 시 약 $1 ~ $2

### 비용 절감 팁

1. **캐싱 활용**: 수정하지 않은 케이스는 재번역하지 않음
2. **선택적 번역**: 필요한 케이스만 번역 조회
3. **일괄 번역 지양**: 개별 케이스 조회 시에만 번역 수행

## 문제 해결

### API 키가 설정되지 않은 경우

**증상**: 로그에 "OPENAI_API_KEY 환경 변수가 설정되지 않았습니다." 경고 출력

**해결**:
1. `.env` 파일에 `OPENAI_API_KEY` 추가
2. 애플리케이션 재시작

### 번역이 작동하지 않는 경우

**확인 사항**:
1. OpenAI API 키가 유효한지 확인
2. API 사용량 한도를 초과하지 않았는지 확인
3. 로그 파일(`logs/quickrail-error.log`) 확인

**로그 확인**:
```bash
# 최근 오류 로그 확인
tail -f logs/quickrail-error.log
```

### 번역 품질 개선

현재 설정:
- `temperature=0.3`: 일관성 있는 번역
- `max_tokens=2000`: 긴 텍스트 지원

필요시 `app/utils/translator.py`에서 조정 가능

## API 엔드포인트

### 번역 조회

```http
GET /api/cases/{case_id}/translation?lang={target_lang}
```

**파라미터**:
- `case_id`: 케이스 ID
- `target_lang`: 대상 언어 (`ko` 또는 `en`)

**응답**:
```json
{
  "case_id": 123,
  "source_lang": "ko",
  "target_lang": "en",
  "title": "Translated title",
  "steps": "Translated steps",
  "expected_result": "Translated expected result",
  "cached": true,
  "updated_at": "2025-12-31T15:00:00"
}
```

## 데이터베이스 스키마

### case_translations 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER | 기본 키 |
| case_id | INTEGER | 케이스 ID (외래 키) |
| source_lang | VARCHAR(10) | 원본 언어 |
| target_lang | VARCHAR(10) | 대상 언어 |
| title | VARCHAR(500) | 번역된 제목 |
| steps | TEXT | 번역된 스텝 |
| expected_result | TEXT | 번역된 예상 결과 |
| created_at | DATETIME | 생성 시간 |
| updated_at | DATETIME | 수정 시간 |

**제약 조건**:
- `case_id + target_lang`: UNIQUE (케이스당 언어별 1개의 번역만 저장)
- `case_id`: ON DELETE CASCADE (케이스 삭제 시 번역도 함께 삭제)

## 향후 개선 계획

1. **비동기 번역**: Celery 등을 사용한 백그라운드 번역 처리
2. **추가 언어 지원**: 일본어, 중국어 등
3. **번역 품질 평가**: 사용자 피드백 수집
4. **일괄 번역**: 여러 케이스를 한 번에 번역하는 기능
5. **번역 히스토리**: 번역 변경 이력 추적

## 참고 자료

- [OpenAI API 문서](https://platform.openai.com/docs/api-reference)
- [GPT-3.5 가격 정책](https://openai.com/pricing)
- [Flask-SQLAlchemy 문서](https://flask-sqlalchemy.palletsprojects.com/)


