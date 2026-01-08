# OpenAI 모델 선택 기능

## 개요
번역에 사용할 OpenAI 모델을 선택할 수 있는 기능입니다. 모델별 가격 정보를 제공하여 비용 효율적인 선택을 지원합니다.

## 주요 기능

### 1. 지원 모델 목록
다양한 OpenAI 모델을 지원하며, 각 모델의 가격과 특징을 확인할 수 있습니다.

| 모델 ID | 이름 | 입력 가격 | 출력 가격 | 설명 | 추천 |
|---------|------|-----------|-----------|------|------|
| `gpt-4o-mini` | GPT-4o Mini | $0.15 / 1M | $0.60 / 1M | GPT-4 수준의 품질, 저렴한 가격 | ⭐ 추천 |
| `gpt-3.5-turbo` | GPT-3.5 Turbo | $0.50 / 1M | $1.50 / 1M | 빠르고 저렴한 모델 | |
| `gpt-3.5-turbo-0125` | GPT-3.5 Turbo (0125) | $0.50 / 1M | $1.50 / 1M | GPT-3.5 최신 버전 | |
| `gpt-4o` | GPT-4o | $2.50 / 1M | $10.00 / 1M | 최신 GPT-4 모델, 높은 품질 | |
| `gpt-4-turbo` | GPT-4 Turbo | $10.00 / 1M | $30.00 / 1M | GPT-4 Turbo, 매우 높은 품질 | |

### 2. 추천 모델: GPT-4o Mini
- **가격**: 입력 $0.15 / 1M tokens, 출력 $0.60 / 1M tokens
- **특징**: GPT-4 수준의 품질을 저렴한 가격에 제공
- **용도**: 간단한 번역 작업에 최적
- **비용 절감**: GPT-3.5-turbo 대비 약 70% 저렴

### 3. 모델별 가격 정보 관리
`app/utils/model_pricing.py`에서 모델별 가격 정보를 중앙 관리합니다.

**제공 기능:**
- `get_model_list()`: 사용 가능한 모델 목록 반환
- `get_model_info(model_id)`: 특정 모델 정보 조회
- `calculate_cost(model_id, input_tokens, output_tokens)`: 정확한 비용 계산
- `get_cheapest_model()`: 가장 저렴한 모델 반환
- `get_recommended_model()`: 추천 모델 반환

### 4. 번역 프롬프트별 모델 설정
각 번역 프롬프트마다 다른 모델을 설정할 수 있습니다.

**설정 방법:**
1. `/settings` 페이지 접속
2. "번역 프롬프트" 탭 선택
3. 프롬프트 편집 또는 새로 생성
4. "OpenAI 모델" 드롭다운에서 원하는 모델 선택
5. 모델 정보 (가격, 설명) 확인
6. 저장

### 5. 실시간 비용 추적
번역 수행 시 실제 토큰 사용량과 비용을 정확하게 기록합니다.

**기록 정보:**
- 사용된 모델
- 입력 토큰 수
- 출력 토큰 수
- 총 토큰 수
- 정확한 비용 (USD)

## 데이터베이스 변경사항

### TranslationPrompt 모델
```python
class TranslationPrompt(db.Model):
    # ... 기존 필드 ...
    model = db.Column(db.String(50), default='gpt-4o-mini')  # 추가됨
```

### TranslationUsage 모델
```python
class TranslationUsage(db.Model):
    # ... 기존 필드 ...
    model = db.Column(db.String(50), default='gpt-3.5-turbo')  # 실제 사용 모델 기록
    cost = db.Column(db.Float, default=0.0)  # 정확한 비용 계산
```

## API 엔드포인트

### GET /api/translation-models
사용 가능한 OpenAI 모델 목록을 조회합니다.

**권한**: Admin, Super Admin

**응답 예시:**
```json
[
  {
    "id": "gpt-4o-mini",
    "name": "GPT-4o Mini",
    "description": "GPT-4 수준의 품질, 저렴한 가격 (추천)",
    "input_price": 0.15,
    "output_price": 0.60,
    "recommended": true
  },
  ...
]
```

## 사용 예시

### 1. 프롬프트 생성 시 모델 선택
```javascript
// 프론트엔드에서 모델 선택
const data = {
    name: 'my-prompt',
    system_prompt: '...',
    user_prompt_template: '...',
    model: 'gpt-4o-mini'  // 모델 선택
};

await fetch('/api/translation-prompts', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
});
```

### 2. 번역 수행 시 자동 모델 사용
```python
# translator.py에서 자동으로 처리
prompt_config = get_active_prompt()
model = prompt_config.get('model', 'gpt-4o-mini')

response = client.chat.completions.create(
    model=model,  # 프롬프트에 설정된 모델 사용
    messages=[...]
)
```

### 3. 비용 계산
```python
from app.utils.model_pricing import calculate_cost

# 정확한 비용 계산
cost = calculate_cost('gpt-4o-mini', input_tokens=100, output_tokens=50)
# cost = 0.000045 (USD)
```

## 비용 비교 예시

**100,000 토큰 번역 시 (입력 60%, 출력 40%)**

| 모델 | 입력 비용 | 출력 비용 | 총 비용 | 절감률 |
|------|-----------|-----------|---------|--------|
| GPT-4o Mini | $0.009 | $0.024 | **$0.033** | 기준 |
| GPT-3.5 Turbo | $0.030 | $0.060 | $0.090 | -173% |
| GPT-4o | $0.150 | $0.400 | $0.550 | -1567% |
| GPT-4 Turbo | $0.600 | $1.200 | $1.800 | -5355% |

**결론**: GPT-4o Mini가 가장 비용 효율적입니다! 🎯

## UI 변경사항

### 설정 페이지 - 프롬프트 편집 모달
1. **모델 선택 드롭다운** 추가
   - 모든 사용 가능한 모델 표시
   - 추천 모델에 ⭐ 표시

2. **모델 정보 패널** 추가
   - 선택한 모델의 상세 정보 표시
   - 입력/출력 가격 정보
   - 모델 설명
   - 추천 모델은 녹색 배경

3. **저장 시 확인 메시지**
   - 선택한 모델 이름 표시

## 마이그레이션

```bash
# 마이그레이션 생성
flask db migrate -m "Add model field to TranslationPrompt"

# 마이그레이션 적용
flask db upgrade

# 또는 직접 컬럼 추가
python add_model_column.py
```

## 파일 변경사항

### 새로 추가된 파일
1. `app/utils/model_pricing.py` - 모델 가격 정보 관리
2. `MODEL_SELECTION_FEATURE.md` - 이 문서

### 수정된 파일
1. `app/models.py`
   - `TranslationPrompt.model` 필드 추가

2. `app/utils/translator.py`
   - `get_active_prompt()`: 모델 정보 포함
   - `translate_text()`: 프롬프트의 모델 사용, 정확한 비용 계산

3. `app/routes/api.py`
   - `GET /api/translation-models` 엔드포인트 추가
   - 프롬프트 CRUD에 모델 필드 포함

4. `app/templates/main/settings.html`
   - 모델 선택 드롭다운 추가
   - 모델 정보 표시 패널 추가
   - JavaScript: 모델 목록 로드 및 관리

5. `migrations/versions/a5632aa01ff6_add_model_field_to_translationprompt.py`
   - 새 마이그레이션 파일

## 권장 사항

### 용도별 모델 선택
1. **일반 번역** (추천): `gpt-4o-mini`
   - 품질과 가격의 최적 균형
   - 대부분의 번역 작업에 적합

2. **빠른 번역**: `gpt-3.5-turbo`
   - 응답 속도가 중요한 경우
   - 간단한 텍스트 번역

3. **고품질 번역**: `gpt-4o`
   - 전문 용어가 많은 경우
   - 문맥 이해가 중요한 경우

4. **최고 품질**: `gpt-4-turbo`
   - 매우 복잡한 번역
   - 비용보다 품질이 우선인 경우

### 비용 절감 팁
1. **GPT-4o Mini 사용**: 기본 번역에 최적
2. **프롬프트 최적화**: 불필요한 설명 제거
3. **배치 번역**: 여러 텍스트를 한 번에 번역
4. **사용량 모니터링**: 정기적으로 비용 확인

## 주의사항

1. **모델 가격 변동**: OpenAI의 가격 정책 변경 시 `model_pricing.py` 업데이트 필요
2. **모델 가용성**: 일부 모델은 지역/계정에 따라 사용 불가할 수 있음
3. **품질 vs 비용**: 용도에 맞는 모델 선택 중요
4. **기존 프롬프트**: 기본값으로 `gpt-4o-mini` 설정됨

## 향후 개선 사항

1. **모델 성능 비교**: A/B 테스트 기능
2. **자동 모델 선택**: 텍스트 복잡도에 따라 자동 선택
3. **예산 관리**: 모델별 예산 설정
4. **실시간 가격 조회**: OpenAI API에서 최신 가격 가져오기
5. **모델 추천 시스템**: 사용 패턴 기반 최적 모델 추천


