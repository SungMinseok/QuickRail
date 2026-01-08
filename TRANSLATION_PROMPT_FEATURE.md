# 번역 프롬프트 설정 기능 구현 완료

## 개요

관리자가 번역 시 사용되는 OpenAI 프롬프트를 웹 UI에서 직접 관리할 수 있는 기능을 구현했습니다.

## 주요 기능

### 1. 설정 페이지
- **위치**: 네비게이션 바 → ⚙️ 설정
- **접근 권한**: Super Admin, Admin만 접근 가능
- **일반 사용자**: 접근 시 403 Forbidden

### 2. 번역 프롬프트 관리
- ✅ **프롬프트 목록 조회**: 저장된 모든 프롬프트 확인
- ✅ **프롬프트 생성**: 새로운 번역 규칙 추가
- ✅ **프롬프트 편집**: 기존 프롬프트 수정
- ✅ **프롬프트 활성화**: 사용할 프롬프트 선택
- ✅ **프롬프트 삭제**: 불필요한 프롬프트 제거 (활성 프롬프트는 삭제 불가)

### 3. 프롬프트 구성 요소

#### 시스템 프롬프트
AI의 역할과 번역 스타일을 정의합니다.

**예시**:
```
You are a professional translator specializing in software testing documentation.
All test case titles must start with "Check if" in English.
```

#### 사용자 프롬프트 템플릿
실제 번역 요청 시 사용되는 템플릿입니다.

**변수**:
- `{source_lang}`: 원본 언어 (Korean, English)
- `{target_lang}`: 대상 언어 (Korean, English)
- `{text}`: 번역할 텍스트

**예시**:
```
Translate the following text from {source_lang} to {target_lang}.
Keep the same formatting and structure. Only provide the translation, no explanations.

IMPORTANT RULES:
- If translating to English, all test case titles MUST start with "Check if"
- Maintain the original meaning while following this format

Text to translate:
{text}
```

## 구현 내용

### 1. 데이터베이스 모델 (`app/models.py`)

```python
class TranslationPrompt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)  # 프롬프트 이름
    system_prompt = db.Column(db.Text)  # 시스템 프롬프트
    user_prompt_template = db.Column(db.Text)  # 사용자 프롬프트 템플릿
    is_active = db.Column(db.Boolean)  # 활성화 여부
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)
```

### 2. 설정 페이지 (`app/templates/main/settings.html`)

**기능**:
- 현재 활성 프롬프트 표시
- 프롬프트 목록 테이블
- 프롬프트 편집 모달
- 실시간 CRUD 작업

### 3. API 엔드포인트 (`app/routes/api.py`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/translation-prompts` | 프롬프트 목록 조회 |
| POST | `/api/translation-prompts` | 새 프롬프트 생성 |
| GET | `/api/translation-prompts/<id>` | 프롬프트 상세 조회 |
| PUT | `/api/translation-prompts/<id>` | 프롬프트 수정 |
| DELETE | `/api/translation-prompts/<id>` | 프롬프트 삭제 |
| POST | `/api/translation-prompts/<id>/activate` | 프롬프트 활성화 |

### 4. 번역 유틸리티 통합 (`app/utils/translator.py`)

```python
def get_active_prompt():
    """활성화된 번역 프롬프트를 가져옵니다."""
    prompt = TranslationPrompt.query.filter_by(is_active=True).first()
    if prompt:
        return {
            'system_prompt': prompt.system_prompt,
            'user_prompt_template': prompt.user_prompt_template
        }
    # 기본 프롬프트 반환
    return {...}

def translate_text(text, source_lang, target_lang):
    # 활성 프롬프트 가져오기
    prompt_config = get_active_prompt()
    
    # 템플릿 변수 치환
    user_prompt = prompt_config['user_prompt_template'].format(
        source_lang=lang_names[source_lang],
        target_lang=lang_names[target_lang],
        text=text
    )
    
    # OpenAI API 호출
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": prompt_config['system_prompt']},
            {"role": "user", "content": user_prompt}
        ],
        ...
    )
```

### 5. 네비게이션 바 업데이트 (`app/templates/base.html`)

```html
{% if current_user.role in ['Super Admin', 'admin'] %}
<a href="{{ url_for('main.settings') }}" class="navbar-link">⚙️ 설정</a>
{% endif %}
```

## 사용 방법

### 1. 설정 페이지 접근

1. Super Admin 또는 Admin 계정으로 로그인
2. 네비게이션 바에서 "⚙️ 설정" 클릭
3. "번역 프롬프트" 탭 선택 (기본 선택됨)

### 2. 새 프롬프트 생성

1. "+ 새 프롬프트 추가" 버튼 클릭
2. 프롬프트 정보 입력:
   - **이름**: 영문, 숫자, 하이픈만 사용 (예: `check-if-style`)
   - **시스템 프롬프트**: AI의 역할 정의
   - **사용자 프롬프트 템플릿**: 번역 요청 템플릿
3. "저장" 버튼 클릭

### 3. 프롬프트 활성화

1. 프롬프트 목록에서 원하는 프롬프트의 "활성화" 버튼 클릭
2. 확인 메시지 확인
3. 페이지 새로고침 → 활성 프롬프트 변경 확인

### 4. 프롬프트 편집

1. 프롬프트 목록에서 "편집" 버튼 클릭
2. 내용 수정
3. "저장" 버튼 클릭

### 5. 프롬프트 삭제

1. 비활성 프롬프트의 "삭제" 버튼 클릭
2. 확인 메시지 확인
3. 삭제 완료

**주의**: 활성 프롬프트는 삭제할 수 없습니다. 먼저 다른 프롬프트를 활성화한 후 삭제하세요.

## 기본 프롬프트

시스템에는 2개의 기본 프롬프트가 포함되어 있습니다:

### 1. default (활성)
표준 번역 프롬프트

**시스템 프롬프트**:
```
You are a professional translator specializing in software testing documentation.
```

**사용자 프롬프트 템플릿**:
```
Translate the following text from {source_lang} to {target_lang}.
Keep the same formatting and structure. Only provide the translation, no explanations.

Text to translate:
{text}
```

### 2. check-if-style (비활성)
모든 케이스 제목이 "Check if"로 시작하도록 강제하는 프롬프트

**시스템 프롬프트**:
```
You are a professional translator specializing in software testing documentation.
All test case titles must start with "Check if" in English.
```

**사용자 프롬프트 템플릿**:
```
Translate the following text from {source_lang} to {target_lang}.
Keep the same formatting and structure. Only provide the translation, no explanations.

IMPORTANT RULES:
- If translating to English, all test case titles MUST start with "Check if"
- Maintain the original meaning while following this format

Text to translate:
{text}
```

## 프롬프트 작성 팁

### 1. 명확한 지시사항
```
IMPORTANT RULES:
- All test cases must start with "Check if"
- Use present tense
- Be concise and specific
```

### 2. 형식 유지
```
Keep the same formatting and structure.
Preserve line breaks and bullet points.
```

### 3. 도메인 특화
```
Use software testing terminology.
Common terms:
- Test case → 테스트 케이스
- Expected result → 예상 결과
```

### 4. 일관성 강조
```
Maintain consistency with previous translations.
Use the same terminology throughout.
```

## 권한 관리

| 역할 | 설정 페이지 접근 | 프롬프트 조회 | 프롬프트 편집 |
|------|-----------------|--------------|--------------|
| Super Admin | ✅ | ✅ | ✅ |
| Admin | ✅ | ✅ | ✅ |
| Author | ❌ | ❌ | ❌ |
| Viewer | ❌ | ❌ | ❌ |

**접근 제어**:
- 일반 사용자가 `/settings` 접근 시 → 403 Forbidden
- API 엔드포인트도 동일한 권한 체크 적용

## 로깅

모든 프롬프트 관련 작업은 로그에 기록됩니다:

```
[INFO] 번역 프롬프트 생성: check-if-style by admin@example.com
[INFO] 번역 프롬프트 수정: default by admin@example.com
[INFO] 번역 프롬프트 활성화: check-if-style by admin@example.com
[INFO] 번역 프롬프트 삭제: old-prompt by admin@example.com
```

로그 위치: `logs/quickrail.log`

## 데이터베이스 마이그레이션

```bash
# 마이그레이션 생성 (이미 완료됨)
flask db migrate -m "Add TranslationPrompt model"

# 마이그레이션 적용 (이미 완료됨)
flask db upgrade

# 기본 프롬프트 추가
python init_translation_prompts.py
```

## 파일 변경 사항

### 신규 파일
- ✅ `app/templates/main/settings.html` - 설정 페이지
- ✅ `init_translation_prompts.py` - 기본 프롬프트 초기화 스크립트
- ✅ `TRANSLATION_PROMPT_FEATURE.md` - 이 문서

### 수정 파일
- ✅ `app/models.py` - TranslationPrompt 모델 추가
- ✅ `app/routes/main.py` - settings 라우트 추가
- ✅ `app/routes/api.py` - 프롬프트 관리 API 추가
- ✅ `app/utils/translator.py` - 활성 프롬프트 적용
- ✅ `app/templates/base.html` - 네비게이션 바에 설정 버튼 추가

## 테스트 시나리오

### 1. 기본 동작 테스트
1. Admin으로 로그인
2. 설정 페이지 접근
3. 현재 활성 프롬프트 확인 (default)
4. 새 케이스 생성 → 자동 번역 확인

### 2. 프롬프트 변경 테스트
1. "check-if-style" 프롬프트 활성화
2. 한국어로 케이스 생성: "로그인 기능 테스트"
3. 영어 번역 확인: "Check if login functionality works"

### 3. 권한 테스트
1. Author 계정으로 로그인
2. `/settings` 접근 시도
3. 403 Forbidden 확인

### 4. CRUD 테스트
1. 새 프롬프트 생성
2. 프롬프트 편집
3. 프롬프트 활성화
4. 프롬프트 삭제 (비활성 프롬프트만)

## 주의사항

### 1. 활성 프롬프트 삭제 불가
- 활성 프롬프트는 삭제할 수 없습니다
- 다른 프롬프트를 먼저 활성화해야 합니다

### 2. 프롬프트 이름 중복 불가
- 프롬프트 이름은 고유해야 합니다
- 영문, 숫자, 하이픈만 사용 권장

### 3. 템플릿 변수 필수
- `{source_lang}`, `{target_lang}`, `{text}` 변수 사용 권장
- 변수 누락 시 번역 오류 발생 가능

### 4. 프롬프트 테스트
- 새 프롬프트 활성화 후 반드시 테스트
- 번역 품질 확인 후 실사용

## 향후 개선 사항

### 단기
1. ⏳ 프롬프트 미리보기 기능
2. ⏳ 프롬프트 복제 기능
3. ⏳ 프롬프트 버전 관리

### 중기
1. ⏳ 프롬프트 A/B 테스트
2. ⏳ 번역 품질 평가 지표
3. ⏳ 프로젝트별 프롬프트 설정

### 장기
1. ⏳ AI 기반 프롬프트 최적화
2. ⏳ 다국어 프롬프트 지원
3. ⏳ 프롬프트 마켓플레이스

---

**구현 완료일**: 2025-12-31  
**버전**: 1.0.0  
**관련 문서**: `TRANSLATION_SETUP.md`, `TRANSLATION_FEATURE_SUMMARY.md`


