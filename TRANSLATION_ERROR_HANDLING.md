# 번역 에러 처리 구현 완료

## 개요

번역 실패 시 사용자에게 명확한 에러 메시지를 표시하도록 개선했습니다.

## 구현 내용

### 1. TranslationError 예외 클래스 추가 (`app/utils/translator.py`)

```python
class TranslationError(Exception):
    """번역 오류 예외"""
    pass
```

### 2. 번역 실패 시 예외 발생

#### OpenAI 클라이언트 없음
```python
if not client:
    error_msg = 'OpenAI API 키가 설정되지 않았습니다. 관리자에게 문의하세요.'
    logger.error(error_msg)
    raise TranslationError(error_msg)
```

#### OpenAI API 호출 실패
```python
except Exception as e:
    # API 키 인증 오류
    if 'authentication' in str(e).lower() or 'api_key' in str(e).lower():
        raise TranslationError('OpenAI API 키가 유효하지 않습니다. 관리자에게 문의하세요.')
    
    # 사용량 한도 초과
    elif 'rate_limit' in str(e).lower():
        raise TranslationError('OpenAI API 사용량 한도를 초과했습니다. 잠시 후 다시 시도하세요.')
    
    # 크레딧 부족
    elif 'insufficient_quota' in str(e).lower():
        raise TranslationError('OpenAI API 크레딧이 부족합니다. 관리자에게 문의하세요.')
    
    # 기타 오류
    else:
        raise TranslationError(f'번역 중 오류가 발생했습니다: {str(e)}')
```

### 3. API 엔드포인트 에러 처리 (`app/routes/api.py`)

#### 케이스 생성 시
```python
translation_error = None
try:
    # 번역 수행
    translated = translate_case({...}, source_lang, target_lang)
    # 번역 저장
    ...
except TranslationError as e:
    translation_error = str(e)
    current_app.logger.error(f'케이스 {case.id} 번역 실패: {e}')
    db.session.rollback()

# 응답에 경고 포함
if translation_error:
    response_data['translation_warning'] = translation_error

return jsonify(response_data), 201
```

**특징**:
- ✅ 번역 실패해도 케이스 생성은 성공
- ✅ `translation_warning` 필드로 에러 전달

#### 케이스 수정 시
```python
translation_error = None
if any(key in data for key in ['title', 'steps', 'expected_result']):
    try:
        # 번역 업데이트
        ...
    except TranslationError as e:
        translation_error = str(e)
        db.session.rollback()

response_data = {'status': 'saved', 'updated_at': ...}
if translation_error:
    response_data['translation_warning'] = translation_error

return jsonify(response_data)
```

#### 번역 조회 시
```python
try:
    # 번역 생성
    translated = translate_case({...}, source_lang, target_lang)
    # 번역 저장 및 반환
    ...
except TranslationError as e:
    return jsonify({'error': str(e)}), 500
except Exception as e:
    return jsonify({'error': f'번역 중 예기치 않은 오류가 발생했습니다: {str(e)}'}), 500
```

### 4. 프론트엔드 에러 표시 (`app/templates/main/cases.html`)

#### 케이스 생성 시 경고 표시
```javascript
const newCase = await response.json();

// 번역 경고가 있으면 표시
if (newCase.translation_warning) {
    alert('⚠️ 번역 경고\n\n' + 
          newCase.translation_warning + 
          '\n\n케이스는 정상적으로 생성되었습니다.');
}
```

#### 언어 변경 시 에러 표시
```javascript
async function changeLanguage(lang) {
    let hasError = false;
    let errorMessage = '';
    
    for (const item of caseItems) {
        try {
            const response = await fetch(`/api/cases/${caseId}/translation?lang=${lang}`);
            if (response.ok) {
                // 번역 표시
                ...
            } else {
                // 에러 응답 처리
                const errorData = await response.json();
                if (!hasError) {
                    hasError = true;
                    errorMessage = errorData.error || '번역 실패';
                }
            }
        } catch (error) {
            if (!hasError) {
                hasError = true;
                errorMessage = error.message || '번역 중 오류가 발생했습니다';
            }
        }
    }
    
    // 에러가 있으면 사용자에게 알림
    if (hasError) {
        alert('⚠️ 번역 오류\n\n' + 
              errorMessage + 
              '\n\n일부 케이스의 번역을 표시할 수 없습니다.');
    }
}
```

#### 케이스 수정 시 모달 내 경고 표시
```javascript
async function updateModalField(field, value) {
    const result = await response.json();
    
    // 번역 경고가 있으면 표시
    if (result.translation_warning) {
        showTranslationWarning(result.translation_warning);
    }
}

function showTranslationWarning(message) {
    const warningDiv = document.createElement('div');
    warningDiv.style.cssText = 'background: #fff3cd; border: 1px solid #ffc107; ...';
    warningDiv.innerHTML = `
        <strong>⚠️ 번역 경고</strong><br>
        ${message}
    `;
    modalBody.insertBefore(warningDiv, modalBody.firstChild);
    
    // 5초 후 자동 제거
    setTimeout(() => warningDiv.remove(), 5000);
}
```

## 에러 메시지 종류

### 1. API 키 미설정
```
OpenAI API 키가 설정되지 않았습니다. 관리자에게 문의하세요.
```

**발생 상황**: `.env` 파일에 `OPENAI_API_KEY`가 없거나 환경 변수가 로드되지 않음

**해결 방법**:
```bash
# .env 파일 생성
echo OPENAI_API_KEY=sk-your-key-here > .env

# 애플리케이션 재시작
python run.py
```

### 2. API 키 인증 실패
```
OpenAI API 키가 유효하지 않습니다. 관리자에게 문의하세요.
```

**발생 상황**: API 키가 잘못되었거나 만료됨

**해결 방법**:
- OpenAI 대시보드에서 새 API 키 발급
- `.env` 파일 업데이트

### 3. 사용량 한도 초과
```
OpenAI API 사용량 한도를 초과했습니다. 잠시 후 다시 시도하세요.
```

**발생 상황**: Rate limit 초과 (분당 요청 수 제한)

**해결 방법**:
- 잠시 대기 후 재시도
- 필요시 OpenAI 플랜 업그레이드

### 4. 크레딧 부족
```
OpenAI API 크레딧이 부족합니다. 관리자에게 문의하세요.
```

**발생 상황**: OpenAI 계정 잔액 부족

**해결 방법**:
- OpenAI 대시보드에서 크레딧 충전
- 결제 정보 확인

### 5. 기타 오류
```
번역 중 오류가 발생했습니다: [상세 오류 메시지]
```

**발생 상황**: 네트워크 오류, 서버 오류 등

**해결 방법**:
- 로그 확인 (`logs/quickrail-error.log`)
- 네트워크 연결 확인
- OpenAI 서비스 상태 확인

## 사용자 경험

### 케이스 생성 시
1. 사용자가 케이스 생성
2. 번역 실패 시:
   - ✅ 케이스는 정상 생성됨
   - ⚠️ 경고 팝업 표시
   - 📝 로그에 에러 기록

### 언어 변경 시
1. 사용자가 언어 드롭다운 변경
2. 번역 실패 시:
   - ⚠️ 에러 팝업 표시
   - 📋 원본 텍스트 유지
   - 📝 콘솔에 에러 로그

### 케이스 수정 시
1. 사용자가 모달에서 케이스 수정
2. 번역 실패 시:
   - ✅ 수정 사항은 정상 저장됨
   - ⚠️ 모달 내 경고 배너 표시 (5초 후 자동 제거)
   - 📝 로그에 에러 기록

## 로그 기록

모든 번역 에러는 로그에 기록됩니다:

```
[ERROR] 케이스 123 번역 실패: OpenAI API 키가 설정되지 않았습니다.
[ERROR] 케이스 456 번역 업데이트 실패: OpenAI API 사용량 한도를 초과했습니다.
[ERROR] 케이스 789 번역 실패: OpenAI API 키가 유효하지 않습니다.
```

로그 위치:
- 일반 로그: `logs/quickrail.log`
- 에러 로그: `logs/quickrail-error.log`

## 테스트 시나리오

### 1. API 키 없이 테스트
```bash
# .env 파일에서 OPENAI_API_KEY 제거 또는 주석 처리
# OPENAI_API_KEY=sk-...

# 애플리케이션 재시작
python run.py

# 케이스 생성 시도
# 예상 결과: "OpenAI API 키가 설정되지 않았습니다" 경고 표시
```

### 2. 잘못된 API 키로 테스트
```bash
# .env 파일에 잘못된 키 설정
OPENAI_API_KEY=sk-invalid-key

# 애플리케이션 재시작
python run.py

# 케이스 생성 시도
# 예상 결과: "OpenAI API 키가 유효하지 않습니다" 경고 표시
```

### 3. 언어 변경 시 에러 테스트
```bash
# API 키 없이 실행
# 케이스 생성 (번역 실패)
# 언어를 English로 변경
# 예상 결과: "OpenAI API 키가 설정되지 않았습니다" 에러 팝업
```

## 파일 변경 사항

### 수정 파일
- ✅ `app/utils/translator.py` - TranslationError 예외 추가, 에러 처리 개선
- ✅ `app/routes/api.py` - 번역 에러 캐치 및 응답에 포함
- ✅ `app/templates/main/cases.html` - 프론트엔드 에러 표시

### 신규 파일
- ✅ `TRANSLATION_ERROR_HANDLING.md` - 이 문서

## 주의사항

### 1. 케이스 생성/수정은 항상 성공
번역 실패해도 케이스 생성/수정은 정상적으로 처리됩니다.
- ✅ 데이터 손실 방지
- ⚠️ 번역만 실패

### 2. 원본 텍스트 유지
번역 실패 시 원본 텍스트가 그대로 표시됩니다.
- 한국어 케이스 → 영어 선택 시 실패 → 한국어 그대로 표시

### 3. 로그 확인 필수
에러 발생 시 로그를 확인하여 정확한 원인 파악:
```bash
tail -f logs/quickrail-error.log
```

## 향후 개선 사항

### 단기
1. ⏳ 재시도 로직 추가 (일시적 오류 대응)
2. ⏳ 번역 큐 시스템 (비동기 처리)
3. ⏳ 에러 통계 대시보드

### 중기
1. ⏳ 사용자별 에러 알림 설정
2. ⏳ 번역 실패 케이스 일괄 재시도 기능
3. ⏳ 대체 번역 엔진 지원 (Google Translate, DeepL)

### 장기
1. ⏳ AI 기반 에러 분석 및 자동 복구
2. ⏳ 번역 품질 모니터링
3. ⏳ 프로액티브 에러 방지 시스템

---

**구현 완료일**: 2025-12-31  
**버전**: 1.1.0  
**관련 문서**: `TRANSLATION_SETUP.md`, `TRANSLATION_FEATURE_SUMMARY.md`, `TRANSLATION_PROMPT_FEATURE.md`


