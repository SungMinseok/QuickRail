# CSV Export 한글 깨짐 문제 수정

## 문제 상황
CSV Export 시 한글이 깨지는 문제가 발생했습니다.

## 원인 분석
1. **UTF-8 BOM 누락**: `Content-Type`에 `charset=utf-8-sig`를 설정했지만, 실제 CSV 데이터에 BOM(Byte Order Mark)을 추가하지 않음
2. **파일명 인코딩 문제**: 한글 파일명이 포함될 경우 `Content-Disposition` 헤더에서 인코딩 문제 발생
3. **응답 데이터 타입**: 문자열을 그대로 반환하여 인코딩이 제대로 적용되지 않음

## 수정 내용

### 1. UTF-8 BOM 추가
```python
# 수정 전
csv_data = output.getvalue()

# 수정 후
csv_data = '\ufeff' + output.getvalue()  # UTF-8 BOM 추가
```

**설명**: `\ufeff`는 UTF-8 BOM(Byte Order Mark)으로, Excel이 파일을 UTF-8로 인식하도록 합니다.

### 2. 바이트 인코딩
```python
# 수정 전
response = make_response(output.getvalue())

# 수정 후
response = make_response(csv_data.encode('utf-8'))
```

**설명**: 문자열을 UTF-8 바이트로 명시적으로 인코딩합니다.

### 3. Content-Type 헤더 수정
```python
# 수정 전
response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'

# 수정 후
response.headers['Content-Type'] = 'text/csv; charset=utf-8'
```

**설명**: BOM을 데이터에 직접 추가했으므로 헤더에서는 `utf-8`만 명시합니다.

### 4. 파일명 인코딩 처리
```python
# 수정 전
response.headers['Content-Disposition'] = f'attachment; filename=run_{run.id}_{run.name}.csv'

# 수정 후
from urllib.parse import quote
filename = f'run_{run.id}_{run.name}.csv'
encoded_filename = quote(filename.encode('utf-8'))
response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
```

**설명**: RFC 5987 표준에 따라 파일명을 URL 인코딩하여 한글 파일명을 지원합니다.

## 수정된 전체 코드

```python
@bp.route('/runs/<int:run_id>/export.csv', methods=['GET'])
@login_required
def export_run_csv(run_id):
    """Phase 1: 런 결과 CSV 내보내기"""
    from flask import make_response
    import csv
    from io import StringIO
    from urllib.parse import quote
    
    run = Run.query.get_or_404(run_id)
    
    # CSV 데이터 생성
    output = StringIO()
    writer = csv.writer(output)
    
    # 헤더 및 데이터 작성
    # ... (기존 코드 동일)
    
    # UTF-8 BOM 추가 (Excel에서 한글 깨짐 방지)
    csv_data = '\ufeff' + output.getvalue()
    
    # CSV 응답 생성
    response = make_response(csv_data.encode('utf-8'))
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    
    # 파일명 인코딩 처리 (한글 파일명 지원)
    filename = f'run_{run.id}_{run.name}.csv'
    encoded_filename = quote(filename.encode('utf-8'))
    response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
    
    return response
```

## 테스트 방법

### 1. 한글 제목 케이스로 런 생성
```
런 이름: "테스트 런 - 한글 깨짐 확인"
케이스: 한글 제목이 포함된 케이스 선택
```

### 2. 결과 입력
```
상태: Fail
코멘트: "한글 코멘트 테스트 - 로그인 실패 재현"
버그 링크: "JIRA-한글-123"
```

### 3. CSV Export
- 런 실행 페이지에서 "📥 CSV 내보내기" 버튼 클릭
- 다운로드된 CSV 파일을 Excel로 열기

### 4. 확인 사항
- ✅ Excel에서 한글이 깨지지 않고 정상 표시
- ✅ 파일명에 한글이 포함되어 있어도 정상 다운로드
- ✅ 모든 컬럼의 한글 데이터가 정상 표시
- ✅ 섹션 경로, 케이스 제목, 코멘트, 버그 링크 등 모든 한글 데이터 확인

## 기술적 배경

### UTF-8 BOM이란?
- **BOM (Byte Order Mark)**: 파일의 시작 부분에 추가되는 특수 문자
- **UTF-8 BOM**: `EF BB BF` (3바이트) 또는 유니코드 `U+FEFF`
- **목적**: 텍스트 파일의 인코딩을 명시적으로 표시
- **Excel**: BOM이 있으면 자동으로 UTF-8로 인식

### RFC 5987 파일명 인코딩
- **표준**: HTTP 헤더에서 비ASCII 문자를 포함한 파일명 처리
- **형식**: `filename*=charset'lang'encoded-filename`
- **예시**: `filename*=UTF-8''run_1_%ED%85%8C%EC%8A%A4%ED%8A%B8.csv`
- **지원**: 대부분의 최신 브라우저에서 지원

## 관련 이슈
- Phase 1 테스트 케이스: [TC-P1-015] Excel에서 한글 깨짐 없이 열기

## 참고 문서
- RFC 5987: https://tools.ietf.org/html/rfc5987
- UTF-8 BOM: https://en.wikipedia.org/wiki/Byte_order_mark
- Python CSV Module: https://docs.python.org/3/library/csv.html

## 수정 일시
- 2026-01-05

## 수정자
- AI Assistant (Cursor)


