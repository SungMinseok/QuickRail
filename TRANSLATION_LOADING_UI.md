# 번역 로딩 UI 및 디버깅 개선

## 개요
번역 진행 상황을 사용자에게 실시간으로 표시하고, 번역 실패 시 상세한 정보를 제공하는 기능입니다.

## 주요 기능

### 1. 번역 로딩 오버레이
언어를 변경하면 전체 화면을 덮는 로딩 오버레이가 표시됩니다.

**표시 정보:**
- 🌐 번역 중 아이콘
- 진행률 바 (0% ~ 100%)
- 현재 진행 상황 (예: 5 / 18)

**UI 특징:**
- 반투명 검은색 배경
- 중앙에 흰색 카드
- 부드러운 애니메이션
- 사용자 입력 차단 (번역 완료까지)

### 2. 실시간 진행률 업데이트
각 케이스의 번역이 완료될 때마다 진행률이 업데이트됩니다.

```
번역 중...
[████████████░░░░░░░░] 12 / 18
```

### 3. 번역 결과 요약
번역 완료 후 결과를 요약하여 표시합니다.

**성공 시:**
- 조용히 완료 (알림 없음)

**일부 실패 시:**
```
⚠️ 번역 완료

성공: 15/18개
실패: 3개

OpenAI API 키가 설정되지 않았습니다. 관리자에게 문의하세요.

일부 케이스의 번역을 표시할 수 없습니다.
```

### 4. 상세한 로깅
서버 로그에 번역 과정을 상세하게 기록합니다.

**로그 예시:**
```
[INFO] 번역 요청: 케이스 101, 대상 언어: en
[INFO] 케이스 101 캐시된 번역 반환

[INFO] 번역 요청: 케이스 102, 대상 언어: en
[INFO] 케이스 102 언어 감지: ko -> en
[INFO] 케이스 102 번역 시작...
[INFO] 번역 완료: ko -> en (모델: gpt-4o-mini, 143 tokens, $0.000225)
[INFO] 케이스 102 번역 완료, 저장 중...
[INFO] 케이스 102 번역 저장 완료

[ERROR] 케이스 103 번역 실패 (TranslationError): OpenAI API 키가 설정되지 않았습니다.
```

## 코드 변경사항

### app/templates/main/cases.html

#### 1. changeLanguage() 함수 개선
```javascript
async function changeLanguage(lang) {
    // 로딩 오버레이 표시
    showTranslationLoading();
    
    // 진행 상황 추적
    const caseItems = Array.from(document.querySelectorAll('.case-item'));
    const totalCases = caseItems.length;
    let translatedCount = 0;
    let failedCases = [];
    
    try {
        for (const item of caseItems) {
            // 번역 처리...
            translatedCount++;
            updateTranslationProgress(translatedCount, totalCases);
        }
    } finally {
        hideTranslationLoading();
    }
    
    // 결과 요약 표시
    if (hasError) {
        const successCount = totalCases - failedCases.length;
        alert(`성공: ${successCount}/${totalCases}개\n실패: ${failedCases.length}개`);
    }
}
```

#### 2. 로딩 UI 함수들
```javascript
// 로딩 오버레이 표시
function showTranslationLoading() {
    // 오버레이 생성 및 표시
}

// 로딩 오버레이 숨기기
function hideTranslationLoading() {
    // 오버레이 숨김
}

// 진행률 업데이트
function updateTranslationProgress(current, total) {
    // 진행률 바 및 텍스트 업데이트
}
```

### app/routes/api.py

#### get_case_translation() 함수 개선
```python
@bp.route('/cases/<int:case_id>/translation', methods=['GET'])
@login_required
def get_case_translation(case_id):
    # 상세한 로깅 추가
    current_app.logger.info(f'번역 요청: 케이스 {case_id}, 대상 언어: {target_lang}')
    
    # 캐시 확인
    if translation:
        current_app.logger.info(f'케이스 {case_id} 캐시된 번역 반환')
        return jsonify({...})
    
    # 언어 감지
    source_lang = detect_language(case.title)
    current_app.logger.info(f'케이스 {case_id} 언어 감지: {source_lang} -> {target_lang}')
    
    # 동일 언어 체크
    if source_lang == target_lang:
        current_app.logger.info(f'케이스 {case_id} 동일 언어, 원본 반환')
        return jsonify({..., 'same_language': True})
    
    # 번역 수행
    current_app.logger.info(f'케이스 {case_id} 번역 시작...')
    translated = translate_case(...)
    current_app.logger.info(f'케이스 {case_id} 번역 완료, 저장 중...')
    
    # 저장
    db.session.commit()
    current_app.logger.info(f'케이스 {case_id} 번역 저장 완료')
    
    # 에러 처리
    except TranslationError as e:
        current_app.logger.error(f'케이스 {case_id} 번역 실패 (TranslationError): {e}')
        return jsonify({'error': str(e), 'case_id': case_id}), 500
```

## 사용 시나리오

### 시나리오 1: 정상 번역
1. 사용자가 언어를 "English"로 변경
2. 로딩 오버레이 표시
3. 진행률 바가 0% → 100%로 증가
4. 모든 케이스가 영어로 번역됨
5. 로딩 오버레이 자동 닫힘

### 시나리오 2: 일부 실패
1. 사용자가 언어를 "English"로 변경
2. 로딩 오버레이 표시
3. 진행률 바 증가 (일부 케이스 실패)
4. 로딩 오버레이 닫힘
5. 결과 요약 알림 표시:
   ```
   성공: 15/18개
   실패: 3개
   
   OpenAI API 키가 설정되지 않았습니다.
   ```

### 시나리오 3: 캐시된 번역
1. 이전에 번역했던 언어로 변경
2. 로딩 오버레이 표시 (매우 짧게)
3. 캐시에서 즉시 로드
4. 빠르게 완료

## 디버깅 가이드

### 번역이 안 되는 경우

#### 1. 로그 확인
```bash
# 최근 로그 확인
tail -f logs/quickrail.log

# 에러 로그만 확인
tail -f logs/quickrail-error.log
```

#### 2. 확인할 로그 패턴
```
[INFO] 번역 요청: 케이스 X, 대상 언어: en
```
→ 요청이 도착했는지 확인

```
[INFO] 케이스 X 캐시된 번역 반환
```
→ 캐시가 있는지 확인

```
[INFO] 케이스 X 언어 감지: ko -> en
```
→ 언어가 올바르게 감지되었는지 확인

```
[INFO] 케이스 X 동일 언어, 원본 반환
```
→ 이미 영어인 케이스는 번역하지 않음

```
[ERROR] 케이스 X 번역 실패 (TranslationError): ...
```
→ 번역 실패 원인 확인

#### 3. 일반적인 문제와 해결

**문제 1: API 키 없음**
```
[ERROR] OpenAI API 키가 설정되지 않았습니다.
```
→ `/settings`에서 API 키 설정

**문제 2: 모델 없음**
```
[ERROR] 활성 프롬프트 조회 실패
```
→ `/settings`에서 번역 프롬프트 활성화

**문제 3: 네트워크 오류**
```
[ERROR] 번역 실패: Connection timeout
```
→ 인터넷 연결 확인

**문제 4: 동일 언어**
```
[INFO] 케이스 X 동일 언어, 원본 반환
```
→ 이미 영어인 케이스는 번역되지 않음 (정상)

## 성능 최적화

### 1. 캐싱
- 한 번 번역된 케이스는 `case_translations` 테이블에 저장
- 다음 번에는 즉시 로드 (API 호출 없음)

### 2. 순차 처리
- 케이스를 하나씩 순차적으로 번역
- OpenAI API 레이트 리밋 방지
- 진행 상황 실시간 표시

### 3. 에러 복구
- 일부 케이스 실패해도 계속 진행
- 실패한 케이스 목록 추적
- 최종 결과 요약 제공

## 향후 개선 사항

1. **병렬 번역**: 여러 케이스를 동시에 번역 (속도 향상)
2. **재시도 로직**: 실패한 케이스 자동 재시도
3. **백그라운드 번역**: 페이지 로드 시 자동으로 미리 번역
4. **번역 취소**: 진행 중인 번역 취소 버튼
5. **번역 품질 평가**: 사용자가 번역 품질 평가 가능


