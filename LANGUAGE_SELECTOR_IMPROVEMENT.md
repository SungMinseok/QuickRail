# 언어 선택 개선 - 원본 옵션 제거

## 개요
언어 선택 드롭다운에서 "원본" 옵션을 제거하고, 대신 더 나은 사용자 경험을 제공하는 기능들을 추가했습니다.

## 변경 사항

### 1. 원본 옵션 제거
**이전:**
```
🌐 [원본 ▼]
    - 원본
    - 한국어
    - English
```

**변경 후:**
```
🌐 [한국어 ▼] [📄 원본]
    - 한국어
    - English
```

### 2. 새로운 기능

#### A. 원본 보기 버튼
- 드롭다운 옆에 "📄 원본" 버튼 추가
- 클릭 시 모달로 모든 케이스의 원본 텍스트 표시
- 케이스 번호와 함께 깔끔하게 정리된 형식

**모달 내용:**
```
📄 원본 텍스트
현재 표시된 케이스들의 원본 텍스트입니다.

┌─────────────────────────────┐
│ 케이스 #101                  │
│ 로그인 기능 테스트            │
└─────────────────────────────┘

┌─────────────────────────────┐
│ 케이스 #102                  │
│ 회원가입 기능 테스트          │
└─────────────────────────────┘

                    [닫기]
```

#### B. 툴팁 (Hover)
- 케이스 제목에 마우스를 올리면 원본 텍스트 표시
- 커서가 물음표 모양으로 변경
- 즉시 원본 확인 가능

```
[케이스 제목]  ← 마우스 오버
    ↓
┌─────────────────────┐
│ 원본: 로그인 기능 테스트 │
└─────────────────────┘
```

#### C. 언어 설정 저장
- 사용자가 선택한 언어를 `localStorage`에 저장
- 다음 방문 시 자동으로 이전 선택 언어 적용
- 페이지 새로고침 후에도 유지

#### D. 자동 언어 감지
- 케이스 생성 시 원본 언어 자동 감지
- 한국어 ↔ 영어 번역만 지원
- 동일 언어는 번역하지 않음

## 사용 방법

### 1. 언어 변경
```
1. 드롭다운에서 원하는 언어 선택
2. 자동으로 번역 시작
3. 진행률 표시
4. 완료
```

### 2. 원본 텍스트 확인 (3가지 방법)

**방법 1: 원본 버튼 클릭**
```
[📄 원본] 버튼 클릭
    ↓
모달 팝업
    ↓
모든 케이스의 원본 텍스트 표시
```

**방법 2: 툴팁 (빠른 확인)**
```
케이스 제목에 마우스 오버
    ↓
툴팁으로 원본 표시
```

**방법 3: 언어 전환**
```
한국어 ↔ English 전환
    ↓
원본 언어로 표시됨
```

## 예방책 및 안전장치

### 1. 원본 데이터 보존
- 모든 케이스 제목의 원본은 `data-original-title` 속성에 저장
- 번역 실패 시에도 원본 데이터 유지
- 언어 전환 시 원본 참조

### 2. 언어 설정 저장
```javascript
localStorage.setItem('preferredLanguage', 'ko');
// 다음 방문 시 자동 복원
```

### 3. 툴팁으로 즉시 확인
- 번역된 텍스트가 이상하면 즉시 원본 확인 가능
- 마우스만 올리면 됨

### 4. 원본 보기 모달
- 모든 케이스의 원본을 한 번에 확인
- 비교 및 검증 용이

### 5. 번역 캐시
- 한 번 번역된 내용은 DB에 저장
- 같은 언어로 다시 전환 시 즉시 표시
- API 호출 최소화

## 기술적 세부사항

### HTML 변경
```html
<!-- 이전 -->
<select id="languageSelect" onchange="changeLanguage(this.value)">
    <option value="original">원본</option>
    <option value="ko">한국어</option>
    <option value="en">English</option>
</select>

<!-- 변경 후 -->
<select id="languageSelect" onchange="changeLanguage(this.value)">
    <option value="ko">한국어</option>
    <option value="en">English</option>
</select>
<button onclick="showOriginalTexts()">📄 원본</button>
```

### JavaScript 변경

#### 1. changeLanguage() 함수
```javascript
async function changeLanguage(lang) {
    // 원본 처리 코드 제거
    // if (lang === 'original') { ... }
    
    // 언어 설정 저장 추가
    localStorage.setItem('preferredLanguage', lang);
    
    // 번역 진행...
}
```

#### 2. showOriginalTexts() 함수 추가
```javascript
function showOriginalTexts() {
    // 모달 생성
    const modal = document.createElement('div');
    
    // 모든 케이스의 원본 텍스트 수집
    const caseItems = document.querySelectorAll('.case-item');
    caseItems.forEach(item => {
        const originalTitle = item.querySelector('.case-title').dataset.originalTitle;
        // 모달에 추가
    });
    
    // 모달 표시
    document.body.appendChild(modal);
}
```

#### 3. DOMContentLoaded 개선
```javascript
document.addEventListener('DOMContentLoaded', function() {
    // 저장된 언어 설정 복원
    const preferredLang = localStorage.getItem('preferredLanguage');
    if (preferredLang) {
        document.getElementById('languageSelect').value = preferredLang;
    }
    
    // 툴팁 추가
    document.querySelectorAll('.case-title').forEach(title => {
        title.title = `원본: ${title.dataset.originalTitle}`;
        title.style.cursor = 'help';
    });
});
```

## 사용자 경험 개선

### 이전 (원본 옵션 있음)
```
문제점:
1. 3개 옵션 중 하나를 선택해야 함
2. "원본"이 무엇인지 불명확
3. 원본 ↔ 번역 전환이 번거로움
4. 드롭다운만으로 원본 확인
```

### 변경 후
```
개선점:
1. 2개 언어만 선택 (명확함)
2. 원본은 별도 버튼으로 분리
3. 툴팁으로 즉시 원본 확인
4. 언어 설정 자동 저장
5. 다양한 원본 확인 방법
```

## 워크플로우 비교

### 시나리오 1: 번역 확인
**이전:**
```
1. 영어로 번역
2. 이상한 부분 발견
3. 드롭다운 → "원본" 선택
4. 원본 확인
5. 다시 드롭다운 → "English" 선택
```

**변경 후:**
```
1. 영어로 번역
2. 이상한 부분 발견
3. 마우스 오버 → 툴팁으로 즉시 확인 ✓
   또는
   [📄 원본] 버튼 → 모든 원본 확인 ✓
```

### 시나리오 2: 다음 방문
**이전:**
```
1. 페이지 접속
2. 드롭다운 기본값: "원본"
3. 원하는 언어 선택
```

**변경 후:**
```
1. 페이지 접속
2. 자동으로 이전 선택 언어 적용 ✓
3. 추가 작업 불필요
```

## 장점

### 1. 사용성 향상
- ✅ 명확한 언어 선택 (한국어/영어)
- ✅ 원본 확인 방법 다양화
- ✅ 언어 설정 자동 저장

### 2. 효율성 증가
- ✅ 툴팁으로 즉시 확인
- ✅ 드롭다운 클릭 횟수 감소
- ✅ 모달로 일괄 확인 가능

### 3. 직관성 개선
- ✅ "원본"의 의미가 명확해짐
- ✅ 언어 전환 목적이 분명해짐
- ✅ UI가 더 깔끔해짐

## 주의사항

1. **툴팁 표시 시간**: 브라우저 기본 설정에 따라 다름
2. **모달 스크롤**: 케이스가 많으면 스크롤 필요
3. **언어 감지**: 한국어/영어만 지원

## 향후 개선 가능 사항

1. **다국어 지원**: 일본어, 중국어 등 추가
2. **번역 품질 평가**: 사용자 피드백 수집
3. **번역 히스토리**: 이전 번역 버전 보기
4. **번역 편집**: 번역 결과 직접 수정
5. **AI 모델 선택**: 사용자가 모델 선택 가능


