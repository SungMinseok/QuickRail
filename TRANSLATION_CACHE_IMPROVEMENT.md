# 번역 캐시 개선 - 원본 언어 캐시 저장

## 개요
케이스 생성/수정 시 원본 언어와 번역 언어 모두 캐시에 저장하여, 언어 전환 시 즉시 표시되도록 개선했습니다.

## 문제점

### 이전 시스템
```
케이스 생성 (한국어)
  ↓
원본만 cases 테이블에 저장
  ↓
영어 번역만 case_translations에 저장
  ↓
한국어 선택 시: cases 테이블에서 조회 ✓
영어 선택 시: case_translations에서 조회 ✓
```

**문제:**
- 원본 언어 캐시가 없어서 매번 cases 테이블 참조
- 일관성 없는 데이터 구조
- 번역 실패 시 원본도 표시 안 됨

### 새로운 시스템
```
케이스 생성 (한국어)
  ↓
cases 테이블에 저장
  ↓
case_translations에 2개 저장:
  1. ko → ko (원본 캐시)
  2. ko → en (번역 캐시)
  ↓
한국어 선택 시: case_translations (ko→ko) 조회 ✓
영어 선택 시: case_translations (ko→en) 조회 ✓
```

**개선점:**
- ✅ 모든 언어가 캐시에 저장
- ✅ 일관된 데이터 구조
- ✅ 빠른 조회 속도
- ✅ 번역 실패 시에도 원본 표시

## 구현 내용

### 1. 케이스 생성 시 (POST /api/projects/<project_id>/cases)

#### 이전 코드
```python
# 반대 언어로만 번역
source_lang = detect_language(case.title)
target_lang = 'en' if source_lang == 'ko' else 'ko'

translation = CaseTranslation(
    case_id=case.id,
    source_lang=source_lang,
    target_lang=target_lang,  # 반대 언어만
    title=translated.get('title'),
    ...
)
db.session.add(translation)
```

#### 새로운 코드
```python
source_lang = detect_language(case.title)

# 1. 원본 언어로 캐시 저장
original_translation = CaseTranslation(
    case_id=case.id,
    source_lang=source_lang,
    target_lang=source_lang,  # 원본 언어
    title=case.title,
    steps=case.steps,
    expected_result=case.expected_result
)
db.session.add(original_translation)

# 2. 반대 언어로 번역 및 저장
target_lang = 'en' if source_lang == 'ko' else 'ko'
translated = translate_case({...}, source_lang, target_lang)

translated_cache = CaseTranslation(
    case_id=case.id,
    source_lang=source_lang,
    target_lang=target_lang,  # 반대 언어
    title=translated.get('title'),
    ...
)
db.session.add(translated_cache)
```

### 2. 케이스 수정 시 (PATCH /api/cases/<case_id>)

#### 이전 코드
```python
# 기존 번역(반대 언어만) 삭제
CaseTranslation.query.filter_by(
    case_id=case.id, 
    target_lang=target_lang
).delete()

# 반대 언어로만 재번역
translation = CaseTranslation(...)
```

#### 새로운 코드
```python
# 기존 번역 모두 삭제
CaseTranslation.query.filter_by(case_id=case.id).delete()

# 1. 원본 언어로 캐시 저장
original_translation = CaseTranslation(
    target_lang=source_lang  # 원본
)

# 2. 반대 언어로 번역 및 저장
translated_cache = CaseTranslation(
    target_lang=target_lang  # 번역
)
```

## 데이터 구조

### case_translations 테이블

| id | case_id | source_lang | target_lang | title | ... |
|----|---------|-------------|-------------|-------|-----|
| 1 | 101 | ko | ko | 로그인 테스트 | ... |
| 2 | 101 | ko | en | Login Test | ... |
| 3 | 102 | en | en | Sign Up Test | ... |
| 4 | 102 | en | ko | 회원가입 테스트 | ... |

**설명:**
- 케이스 101: 한국어로 작성 → ko→ko (원본), ko→en (번역)
- 케이스 102: 영어로 작성 → en→en (원본), en→ko (번역)

## 사용 시나리오

### 시나리오 1: 한국어 사용자
```
1. 케이스 생성: "로그인 테스트"
   ↓
2. 자동 저장:
   - cases 테이블: "로그인 테스트"
   - case_translations:
     * ko → ko: "로그인 테스트" (원본 캐시)
     * ko → en: "Login Test" (번역 캐시)
   ↓
3. 언어 선택:
   - 한국어: case_translations (ko→ko) 조회 → "로그인 테스트" ✓
   - English: case_translations (ko→en) 조회 → "Login Test" ✓
```

### 시나리오 2: 영어 사용자
```
1. 케이스 생성: "Sign Up Test"
   ↓
2. 자동 저장:
   - cases 테이블: "Sign Up Test"
   - case_translations:
     * en → en: "Sign Up Test" (원본 캐시)
     * en → ko: "회원가입 테스트" (번역 캐시)
   ↓
3. 언어 선택:
   - English: case_translations (en→en) 조회 → "Sign Up Test" ✓
   - 한국어: case_translations (en→ko) 조회 → "회원가입 테스트" ✓
```

### 시나리오 3: 번역 실패
```
1. 케이스 생성: "로그인 테스트"
   ↓
2. 원본 캐시 저장 성공
   ↓
3. 번역 실패 (API 키 없음)
   ↓
4. 결과:
   - case_translations:
     * ko → ko: "로그인 테스트" (원본 캐시) ✓
     * ko → en: 없음 (번역 실패)
   ↓
5. 언어 선택:
   - 한국어: case_translations (ko→ko) 조회 → "로그인 테스트" ✓
   - English: 캐시 없음 → 실시간 번역 시도
```

## 장점

### 1. 성능 향상
- ✅ 모든 언어가 캐시에 저장
- ✅ 데이터베이스 조회 1회로 완료
- ✅ cases 테이블 조회 불필요

### 2. 일관성
- ✅ 모든 언어가 동일한 테이블에서 조회
- ✅ 동일한 데이터 구조
- ✅ 코드 단순화

### 3. 안정성
- ✅ 번역 실패 시에도 원본 캐시 유지
- ✅ 원본 언어는 항상 표시 가능
- ✅ 데이터 손실 방지

### 4. 확장성
- ✅ 다국어 지원 용이 (일본어, 중국어 등)
- ✅ 캐시 관리 단순화
- ✅ 일관된 API 응답

## API 응답 예시

### GET /api/cases/101/translation?lang=ko
```json
{
  "case_id": 101,
  "source_lang": "ko",
  "target_lang": "ko",
  "title": "로그인 테스트",
  "steps": "1. 로그인 페이지 접속...",
  "expected_result": "로그인 성공",
  "cached": true,
  "updated_at": "2026-01-02T10:00:00"
}
```

### GET /api/cases/101/translation?lang=en
```json
{
  "case_id": 101,
  "source_lang": "ko",
  "target_lang": "en",
  "title": "Login Test",
  "steps": "1. Access login page...",
  "expected_result": "Login successful",
  "cached": true,
  "updated_at": "2026-01-02T10:00:00"
}
```

## 로그 예시

### 케이스 생성 시
```
[INFO] 케이스 105 생성 - 언어 감지: ko
[INFO] 케이스 105 원본 캐시 저장: ko
[INFO] OpenAI 클라이언트 초기화 성공 (키: admin)
[INFO] 번역 완료: ko -> en (모델: gpt-4o-mini, 143 tokens, $0.000225)
[INFO] 케이스 105 번역 완료: ko -> en
```

### 케이스 수정 시
```
[INFO] 케이스 105 수정 - 언어 감지: ko
[INFO] 케이스 105 원본 캐시 업데이트: ko
[INFO] 번역 완료: ko -> en (모델: gpt-4o-mini, 156 tokens, $0.000243)
[INFO] 케이스 105 번역 업데이트 완료: ko -> en
```

### 번역 조회 시
```
[INFO] 번역 요청: 케이스 105, 대상 언어: ko
[INFO] 케이스 105 캐시된 번역 반환
```

## 마이그레이션

기존 케이스들의 원본 캐시를 생성하는 스크립트:

```python
# fix_translation_cache.py (이미 실행 완료)
for case in cases:
    source_lang = detect_language(case.title)
    
    # 원본 캐시 생성
    original_cache = CaseTranslation(
        case_id=case.id,
        source_lang=source_lang,
        target_lang=source_lang,  # 원본
        title=case.title,
        ...
    )
    
    # 번역 캐시 생성
    translated_cache = CaseTranslation(
        case_id=case.id,
        source_lang=source_lang,
        target_lang=target_lang,  # 번역
        ...
    )
```

## 주의사항

1. **디스크 사용량 증가**: 각 케이스마다 2개의 캐시 저장 (원본 + 번역)
2. **초기 생성 시간**: 케이스 생성 시 번역 시간 소요
3. **API 비용**: 케이스 생성/수정 시마다 번역 API 호출

## 향후 개선 사항

1. **다국어 지원**: 일본어, 중국어 등 추가 언어 지원
2. **백그라운드 번역**: 비동기로 번역하여 응답 속도 향상
3. **선택적 번역**: 사용자가 원하는 언어만 번역
4. **캐시 무효화**: 번역 프롬프트 변경 시 캐시 재생성
5. **번역 품질 개선**: 더 나은 모델 사용 또는 프롬프트 최적화

## 결론

이제 모든 케이스가 원본 언어와 번역 언어 모두 캐시에 저장되어, 언어 전환 시 즉시 표시됩니다. 이를 통해 성능, 일관성, 안정성이 모두 향상되었습니다.


