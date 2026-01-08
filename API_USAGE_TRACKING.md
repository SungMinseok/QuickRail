# API 사용량 추적 기능

## 개요
QuickRail에서 OpenAI API 번역 사용량을 정확하게 추적하고 통계를 제공하는 기능입니다.

## 주요 기능

### 1. TranslationUsage 모델
번역 API 호출마다 상세한 사용량 정보를 데이터베이스에 기록합니다.

**저장 정보:**
- `case_id`: 관련 케이스 ID (선택)
- `source_lang`: 원본 언어 (ko, en)
- `target_lang`: 대상 언어 (ko, en)
- `input_tokens`: 입력 토큰 수
- `output_tokens`: 출력 토큰 수
- `total_tokens`: 총 토큰 수
- `model`: 사용된 모델 (gpt-3.5-turbo)
- `cost`: 예상 비용 (USD)
- `user_id`: 요청한 사용자 ID
- `created_at`: 생성 시간

### 2. 자동 사용량 기록
`app/utils/translator.py`의 `translate_text()` 함수가 번역을 수행할 때마다 자동으로 사용량을 기록합니다.

**비용 계산:**
- GPT-3.5-turbo 기준
- Input: $0.0015 / 1K tokens
- Output: $0.002 / 1K tokens

### 3. 사용량 통계 API
`GET /api/api-keys/usage` 엔드포인트를 통해 상세한 사용량 통계를 조회할 수 있습니다.

**제공 통계:**

#### QuickRail 사용량
- **전체 누적**: 총 요청 수, 총 토큰, 누적 비용
- **최근 30일**: 요청 수, 토큰, 비용
- **최근 7일**: 요청 수, 토큰, 비용

#### 일별 상세 통계 (최근 7일)
- 날짜별 요청 수
- 날짜별 토큰 사용량
- 날짜별 비용

#### 언어별 통계 (최근 30일)
- 번역 방향별 (ko→en, en→ko)
- 요청 수
- 토큰 사용량

### 4. 설정 페이지 UI
`/settings` 페이지의 "API 키 관리" 탭에서 "📊 사용량 확인" 버튼을 클릭하면 상세한 사용량 통계를 확인할 수 있습니다.

**표시 정보:**
1. QuickRail 번역 사용량 요약
   - 전체 누적 (배경: 파란색)
   - 최근 30일 (배경: 주황색)
   - 최근 7일 (배경: 녹색)

2. 일별 사용량 테이블
   - 날짜, 요청 수, 토큰, 비용

3. 언어별 사용량 테이블
   - 번역 방향, 요청 수, 토큰

## 데이터베이스 스키마

```sql
CREATE TABLE translation_usage (
    id INTEGER PRIMARY KEY,
    case_id INTEGER,
    source_lang VARCHAR(10) NOT NULL,
    target_lang VARCHAR(10) NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    model VARCHAR(50) DEFAULT 'gpt-3.5-turbo',
    cost FLOAT DEFAULT 0.0,
    user_id INTEGER,
    created_at DATETIME,
    FOREIGN KEY (case_id) REFERENCES cases(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

## 마이그레이션

```bash
# 마이그레이션 생성
flask db migrate -m "Add TranslationUsage model for tracking API usage"

# 마이그레이션 적용
flask db upgrade
```

## 사용 예시

### 번역 수행 시 자동 기록
```python
# translator.py의 translate_text() 함수에서 자동으로 처리
translated = translate_text("안녕하세요", "ko", "en")
# → TranslationUsage 레코드가 자동으로 생성됨
```

### 사용량 조회
```javascript
// 프론트엔드에서 사용량 조회
const response = await fetch('/api/api-keys/usage');
const data = await response.json();

console.log('전체 요청:', data.quickrail_usage.total.requests);
console.log('전체 비용:', data.quickrail_usage.total.cost);
```

## 주의사항

1. **실시간 사용량**: QuickRail 내부에서 추적한 사용량입니다.
2. **OpenAI 대시보드**: 실제 청구 금액은 OpenAI 대시보드에서 확인하세요.
   - https://platform.openai.com/usage
3. **비용 추정**: 표시된 비용은 추정치이며 실제 청구 금액과 다를 수 있습니다.
4. **권한**: Super Admin 및 Admin 계정만 사용량 통계를 조회할 수 있습니다.

## 파일 변경 사항

### 새로 추가된 파일
- `migrations/versions/1fe7d3ba2d6b_add_translationusage_model_for_tracking_.py`

### 수정된 파일
1. `app/models.py`
   - `TranslationUsage` 모델 추가

2. `app/utils/translator.py`
   - `translate_text()` 함수에 사용량 기록 로직 추가
   - OpenAI API 응답에서 토큰 정보 추출
   - 비용 계산 및 DB 저장

3. `app/routes/api.py`
   - `TranslationUsage` 모델 import 추가
   - `api_key_usage()` 함수 완전 재작성
   - QuickRail 자체 사용량 통계 제공

4. `app/templates/main/settings.html`
   - `checkAPIUsage()` 함수 재작성
   - 사용량 표시 UI 개선
   - 일별/언어별 통계 테이블 추가

5. `requirements.txt`
   - `openai==2.14.0` (1.12.0에서 업그레이드)

## 향후 개선 사항

1. **사용량 알림**: 특정 임계값 초과 시 알림 기능
2. **예산 관리**: 월별 예산 설정 및 모니터링
3. **사용자별 통계**: 사용자별 번역 사용량 추적
4. **프로젝트별 통계**: 프로젝트별 번역 비용 분석
5. **그래프 시각화**: Chart.js를 이용한 사용량 그래프


