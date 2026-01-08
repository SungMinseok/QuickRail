# API 키 관리 및 사용량 모니터링 기능 구현 완료

## 개요

Super Admin이 웹 UI에서 OpenAI API 키를 관리하고 사용량을 모니터링할 수 있는 기능을 구현했습니다.

## 주요 기능

### 1. API 키 관리 (Super Admin 전용)
- ✅ **API 키 추가**: 새로운 OpenAI API 키 등록
- ✅ **API 키 편집**: 기존 API 키 수정
- ✅ **API 키 활성화**: 사용할 API 키 선택
- ✅ **API 키 삭제**: 불필요한 API 키 제거 (활성 키는 삭제 불가)
- ✅ **마지막 사용 시간**: 각 키의 마지막 사용 시간 추적

### 2. 사용량 모니터링
- ✅ **총 요청 수**: 최근 30일간 번역 요청 횟수
- ✅ **총 토큰 사용**: 예상 토큰 사용량
- ✅ **예상 비용**: GPT-3.5-turbo 기준 예상 비용
- ✅ **일별 통계**: 최근 7일간 일별 사용량 그래프

### 3. 권한 관리
- ✅ **Super Admin만 접근**: API 키 관리는 Super Admin만 가능
- ✅ **Admin은 프롬프트만**: Admin은 번역 프롬프트만 관리 가능

## 구현 내용

### 1. 데이터베이스 모델 (`app/models.py`)

```python
class APIKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))  # 키 이름
    api_key = db.Column(db.String(500))  # API 키
    is_active = db.Column(db.Boolean)  # 활성화 여부
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)
    last_used_at = db.Column(db.DateTime)  # 마지막 사용 시간
```

### 2. 설정 페이지 UI (`app/templates/main/settings.html`)

#### 탭 구조
```
Super Admin:
  🔑 API 키 관리 (기본 활성)
  🌐 번역 프롬프트

Admin:
  🌐 번역 프롬프트 (기본 활성)
```

#### API 키 관리 섹션
- **현재 활성 API 키**: 초록색 박스로 강조 표시
  - 키 이름
  - API 키 (마스킹: `sk-xxxxxxxx...xxxx`)
  - 마지막 사용 시간
  - "📊 사용량 확인" 버튼

- **사용량 통계**: 노란색 박스
  - 총 요청 수
  - 총 토큰 사용
  - 예상 비용
  - 최근 7일 일별 통계 테이블

- **API 키 목록**: 테이블 형식
  - 이름, API 키, 상태, 마지막 사용, 작업 버튼

#### API 키 편집 모달
- 키 이름 입력
- API 키 입력 (password 타입)
- 보안 주의사항 표시
- OpenAI API 키 발급 링크

### 3. API 엔드포인트 (`app/routes/api.py`)

| 메서드 | 경로 | 설명 | 권한 |
|--------|------|------|------|
| GET | `/api/api-keys` | API 키 목록 조회 | Super Admin |
| POST | `/api/api-keys` | 새 API 키 생성 | Super Admin |
| GET | `/api/api-keys/<id>` | API 키 상세 조회 | Super Admin |
| PUT | `/api/api-keys/<id>` | API 키 수정 | Super Admin |
| DELETE | `/api/api-keys/<id>` | API 키 삭제 | Super Admin |
| POST | `/api/api-keys/<id>/activate` | API 키 활성화 | Super Admin |
| GET | `/api/api-keys/usage` | 사용량 조회 | Super Admin |

### 4. 번역 유틸리티 통합 (`app/utils/translator.py`)

#### API 키 우선순위
```python
def get_openai_client():
    # 1순위: DB에서 활성 API 키 조회
    active_key = APIKey.query.filter_by(is_active=True).first()
    if active_key:
        # 마지막 사용 시간 업데이트
        active_key.last_used_at = datetime.utcnow()
        db.session.commit()
        return OpenAI(api_key=active_key.api_key)
    
    # 2순위: 환경 변수에서 API 키 조회
    api_key = os.environ.get('OPENAI_API_KEY')
    if api_key:
        return OpenAI(api_key=api_key)
    
    return None
```

**특징**:
- DB 우선, 환경 변수는 백업
- 매 번역마다 마지막 사용 시간 자동 업데이트
- 동적 클라이언트 생성 (키 변경 시 재시작 불필요)

## 사용 방법

### 1. API 키 추가

1. Super Admin으로 로그인
2. 네비게이션 바 → "⚙️ 설정" 클릭
3. "🔑 API 키 관리" 탭 선택
4. "+ 새 API 키 추가" 버튼 클릭
5. 정보 입력:
   - **키 이름**: Production, Test 등
   - **API 키**: sk-로 시작하는 OpenAI API 키
6. "저장" 클릭

### 2. API 키 활성화

1. API 키 목록에서 원하는 키의 "활성화" 버튼 클릭
2. 확인 메시지 확인
3. 페이지 새로고침 → 활성 API 키 변경 확인

### 3. 사용량 확인

1. 현재 활성 API 키 박스에서 "📊 사용량 확인" 버튼 클릭
2. 사용량 통계 표시:
   - 총 요청 수
   - 총 토큰 사용
   - 예상 비용
   - 최근 7일 일별 통계

### 4. API 키 편집

1. API 키 목록에서 "편집" 버튼 클릭
2. 키 이름 또는 API 키 수정
3. "저장" 클릭

### 5. API 키 삭제

1. 비활성 API 키의 "삭제" 버튼 클릭
2. 확인 메시지 확인
3. 삭제 완료

**주의**: 활성 API 키는 삭제할 수 없습니다.

## 사용량 계산 방식

### 추정 방식
OpenAI API는 직접적인 사용량 조회 API를 제공하지 않으므로, 다음과 같이 추정합니다:

1. **요청 수**: DB의 `case_translations` 테이블에서 최근 30일 번역 횟수 조회
2. **토큰 수**: 케이스당 평균 500 토큰으로 추정
3. **비용**: GPT-3.5-turbo 가격 기준
   - Input: $0.0015 / 1K tokens
   - Output: $0.002 / 1K tokens
   - 평균: $0.00175 / 1K tokens

### 예시
```
총 요청 수: 150회
총 토큰 사용: 75,000 tokens
예상 비용: $0.1313

최근 7일 사용량:
날짜         요청 수    토큰
2025-12-30    25      12,500
2025-12-29    18       9,000
2025-12-28    32      16,000
...
```

### 정확한 사용량 확인
실제 사용량은 OpenAI 대시보드에서 확인하세요:
https://platform.openai.com/usage

## 보안

### API 키 저장
- ⚠️ **현재**: 평문으로 DB에 저장
- 🔒 **권장**: 향후 암호화 구현 필요

### 접근 제어
- ✅ Super Admin만 API 키 관리 가능
- ✅ Admin은 API 키 탭 자체가 보이지 않음
- ✅ API 엔드포인트에서도 권한 체크

### API 키 마스킹
- UI에서 API 키는 마스킹되어 표시
- 형식: `sk-xxxxxxxx...xxxx` (앞 10자, 뒤 4자만 표시)

## 권한 매트릭스

| 기능 | Super Admin | Admin | Author | Viewer |
|------|-------------|-------|--------|--------|
| API 키 조회 | ✅ | ❌ | ❌ | ❌ |
| API 키 추가 | ✅ | ❌ | ❌ | ❌ |
| API 키 편집 | ✅ | ❌ | ❌ | ❌ |
| API 키 삭제 | ✅ | ❌ | ❌ | ❌ |
| API 키 활성화 | ✅ | ❌ | ❌ | ❌ |
| 사용량 조회 | ✅ | ❌ | ❌ | ❌ |
| 번역 프롬프트 관리 | ✅ | ✅ | ❌ | ❌ |

## 로깅

모든 API 키 관련 작업은 로그에 기록됩니다:

```
[INFO] API 키 생성: Production by admin@example.com
[INFO] API 키 수정: Production by admin@example.com
[INFO] API 키 활성화: Production by admin@example.com
[INFO] API 키 삭제: Test by admin@example.com
[INFO] DB에서 API 키 사용: Production
```

로그 위치: `logs/quickrail.log`

## 마이그레이션

```bash
# 마이그레이션 생성 (이미 완료됨)
flask db migrate -m "Add APIKey model for API key management"

# 마이그레이션 적용 (이미 완료됨)
flask db upgrade
```

## 파일 변경 사항

### 신규 파일
- ✅ `API_KEY_MANAGEMENT_FEATURE.md` - 이 문서

### 수정 파일
- ✅ `app/models.py` - APIKey 모델 추가
- ✅ `app/routes/main.py` - 설정 페이지에 API 키 데이터 추가
- ✅ `app/routes/api.py` - API 키 관리 API 추가
- ✅ `app/templates/main/settings.html` - API 키 관리 UI 추가
- ✅ `app/utils/translator.py` - DB에서 API 키 조회 로직 추가

## 환경 변수 vs DB

### 환경 변수 방식 (기존)
```bash
# .env 파일
OPENAI_API_KEY=sk-...

# 장점: 간단
# 단점: 변경 시 재시작 필요, 웹 UI 없음
```

### DB 방식 (신규)
```python
# DB에 저장
APIKey(name='Production', api_key='sk-...', is_active=True)

# 장점: 웹 UI, 재시작 불필요, 여러 키 관리
# 단점: DB 접근 필요
```

### 우선순위
1. **DB 활성 키** (1순위)
2. **환경 변수** (2순위, 백업용)

## 테스트 시나리오

### 1. API 키 추가 및 활성화
```
1. Super Admin 로그인
2. 설정 → API 키 관리
3. "+ 새 API 키 추가" 클릭
4. 이름: "Test", API 키: "sk-test..." 입력
5. 저장
6. "활성화" 버튼 클릭
7. 케이스 생성 → 번역 확인
```

### 2. 사용량 모니터링
```
1. 여러 케이스 생성 (번역 발생)
2. 설정 → API 키 관리
3. "📊 사용량 확인" 클릭
4. 요청 수, 토큰, 비용 확인
5. 일별 통계 확인
```

### 3. API 키 전환
```
1. 두 개의 API 키 등록 (Production, Test)
2. Production 활성화 → 케이스 생성
3. Test 활성화 → 케이스 생성
4. 각 키의 "마지막 사용" 시간 확인
```

### 4. 권한 테스트
```
1. Admin 계정으로 로그인
2. 설정 페이지 접근
3. API 키 관리 탭이 보이지 않는지 확인
4. 번역 프롬프트 탭만 표시되는지 확인
```

## 주의사항

### 1. API 키 보안
- ⚠️ API 키는 매우 민감한 정보입니다
- 🔒 Super Admin만 접근 가능하도록 설정됨
- 📝 모든 작업이 로그에 기록됨

### 2. 활성 키 삭제 불가
- 활성화된 API 키는 삭제할 수 없습니다
- 다른 키를 먼저 활성화한 후 삭제하세요

### 3. 사용량 추정치
- 표시되는 사용량은 **추정치**입니다
- 정확한 사용량은 OpenAI 대시보드에서 확인하세요

### 4. API 키 형식
- OpenAI API 키는 `sk-`로 시작해야 합니다
- 잘못된 형식의 키는 저장할 수 없습니다

## 향후 개선 사항

### 단기 (1-2주)
1. ⏳ API 키 암호화 저장
2. ⏳ 사용량 알림 (임계값 초과 시)
3. ⏳ API 키 만료일 설정

### 중기 (1-2개월)
1. ⏳ 실시간 사용량 모니터링
2. ⏳ 프로젝트별 API 키 설정
3. ⏳ 비용 예산 설정 및 알림

### 장기 (3개월+)
1. ⏳ 다중 AI 제공자 지원 (Google, DeepL)
2. ⏳ 사용량 기반 자동 키 전환
3. ⏳ 상세 사용량 분석 대시보드

---

**구현 완료일**: 2025-12-31  
**버전**: 1.2.0  
**관련 문서**: `TRANSLATION_SETUP.md`, `TRANSLATION_PROMPT_FEATURE.md`, `TRANSLATION_ERROR_HANDLING.md`


