"""
OpenAI API를 사용한 번역 유틸리티
"""
import os
import logging
from openai import OpenAI
from flask import current_app

logger = logging.getLogger(__name__)


class TranslationError(Exception):
    """번역 오류 예외"""
    pass


# OpenAI 클라이언트는 매번 동적으로 생성
# (DB에서 활성 API 키를 가져오기 위함)
def get_openai_client():
    """OpenAI 클라이언트를 가져옵니다 (DB 또는 환경 변수에서)"""
    api_key_value = None
    api_key_name = None
    
    try:
        # 1순위: DB에서 활성 API 키 조회
        from app.models import APIKey
        from app import db
        
        active_key = APIKey.query.filter_by(is_active=True).first()
        if active_key and active_key.api_key:
            api_key_value = active_key.api_key.strip()
            api_key_name = active_key.name
            
            # 마지막 사용 시간 업데이트
            from datetime import datetime
            active_key.last_used_at = datetime.utcnow()
            db.session.commit()
            
            logger.info(f'DB에서 API 키 사용: {api_key_name}')
    except Exception as e:
        logger.warning(f'DB에서 API 키 조회 실패: {e}')
    
    # 2순위: 환경 변수에서 API 키 조회
    if not api_key_value:
        api_key_value = os.environ.get('OPENAI_API_KEY')
        if api_key_value:
            api_key_value = api_key_value.strip()
            api_key_name = '환경 변수'
            logger.info('환경 변수에서 API 키 사용')
    
    # API 키가 없으면 None 반환
    if not api_key_value:
        logger.warning('API 키를 찾을 수 없습니다 (DB 및 환경 변수 모두 없음)')
        return None
    
    # OpenAI 클라이언트 생성
    try:
        client = OpenAI(api_key=api_key_value)
        logger.info(f'OpenAI 클라이언트 초기화 성공 (키: {api_key_name})')
        return client
    except Exception as e:
        logger.error(f'OpenAI 클라이언트 초기화 실패: {e}')
        return None


def detect_language(text):
    """텍스트의 언어를 감지 (간단한 휴리스틱)"""
    if not text:
        return 'en'
    
    # 한글이 포함되어 있으면 한국어
    korean_chars = sum(1 for char in text if '\uac00' <= char <= '\ud7a3')
    if korean_chars > len(text) * 0.1:  # 10% 이상이 한글이면
        return 'ko'
    return 'en'


def get_active_prompt():
    """활성화된 번역 프롬프트를 가져옵니다."""
    try:
        from app.models import TranslationPrompt
        from app import db
        
        prompt = TranslationPrompt.query.filter_by(is_active=True).first()
        if prompt:
            return {
                'system_prompt': prompt.system_prompt,
                'user_prompt_template': prompt.user_prompt_template,
                'model': prompt.model or 'gpt-4o-mini'
            }
    except Exception as e:
        logger.warning(f'활성 프롬프트 조회 실패: {e}')
    
    # 기본 프롬프트 반환
    return {
        'system_prompt': 'You are a professional translator specializing in software testing documentation.',
        'user_prompt_template': 'Translate the following text from {source_lang} to {target_lang}.\nKeep the same formatting and structure. Only provide the translation, no explanations.\n\nText to translate:\n{text}',
        'model': 'gpt-4o-mini'
    }


def translate_text(text, source_lang, target_lang):
    """
    텍스트를 번역합니다.
    
    Args:
        text: 번역할 텍스트
        source_lang: 원본 언어 ('ko' 또는 'en')
        target_lang: 대상 언어 ('ko' 또는 'en')
    
    Returns:
        번역된 텍스트
        
    Raises:
        TranslationError: 번역 실패 시
    """
    if not text or not text.strip():
        return text
    
    if source_lang == target_lang:
        return text
    
    # OpenAI 클라이언트 가져오기
    client = get_openai_client()
    if not client:
        error_msg = 'OpenAI API 키가 설정되지 않았습니다. 관리자에게 문의하세요.'
        logger.error(error_msg)
        raise TranslationError(error_msg)
    
    try:
        lang_names = {
            'ko': 'Korean',
            'en': 'English'
        }
        
        # 활성 프롬프트 가져오기
        prompt_config = get_active_prompt()
        
        # 사용자 프롬프트 생성 (템플릿 변수 치환)
        user_prompt = prompt_config['user_prompt_template'].format(
            source_lang=lang_names[source_lang],
            target_lang=lang_names[target_lang],
            text=text
        )
        
        # 사용할 모델 결정
        model = prompt_config.get('model', 'gpt-4o-mini')
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt_config['system_prompt']},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=2000
        )
        
        translated = response.choices[0].message.content.strip()
        
        # 사용량 기록
        try:
            from app.models import TranslationUsage
            from app import db
            from flask import has_request_context
            from flask_login import current_user
            from app.utils.model_pricing import calculate_cost
            
            usage = response.usage
            input_tokens = usage.prompt_tokens if hasattr(usage, 'prompt_tokens') else 0
            output_tokens = usage.completion_tokens if hasattr(usage, 'completion_tokens') else 0
            total_tokens = usage.total_tokens if hasattr(usage, 'total_tokens') else 0
            
            # 모델별 가격 계산
            cost = calculate_cost(model, input_tokens, output_tokens)
            
            usage_record = TranslationUsage(
                source_lang=source_lang,
                target_lang=target_lang,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                model=model,
                cost=cost,
                user_id=current_user.id if has_request_context() and current_user.is_authenticated else None
            )
            db.session.add(usage_record)
            db.session.commit()
            
            logger.info(f'번역 완료: {source_lang} -> {target_lang} (모델: {model}, {total_tokens} tokens, ${cost:.6f})')
        except Exception as e:
            logger.warning(f'사용량 기록 실패: {e}')
        
        return translated
        
    except Exception as e:
        error_msg = f'번역 실패: {str(e)}'
        logger.error(error_msg)
        
        # OpenAI API 관련 에러 메시지 개선
        if 'authentication' in str(e).lower() or 'api_key' in str(e).lower():
            raise TranslationError('OpenAI API 키가 유효하지 않습니다. 관리자에게 문의하세요.')
        elif 'rate_limit' in str(e).lower():
            raise TranslationError('OpenAI API 사용량 한도를 초과했습니다. 잠시 후 다시 시도하세요.')
        elif 'insufficient_quota' in str(e).lower():
            raise TranslationError('OpenAI API 크레딧이 부족합니다. 관리자에게 문의하세요.')
        else:
            raise TranslationError(f'번역 중 오류가 발생했습니다: {str(e)}')


def translate_case(case_data, source_lang, target_lang):
    """
    케이스 데이터를 번역합니다.
    
    Args:
        case_data: 케이스 데이터 딕셔너리 (title, steps, expected_result)
        source_lang: 원본 언어
        target_lang: 대상 언어
    
    Returns:
        번역된 케이스 데이터 딕셔너리
    """
    translated = {}
    
    # 제목 번역
    if case_data.get('title'):
        translated['title'] = translate_text(
            case_data['title'],
            source_lang,
            target_lang
        )
    
    # 테스트 단계 번역
    if case_data.get('steps'):
        translated['steps'] = translate_text(
            case_data['steps'],
            source_lang,
            target_lang
        )
    
    # 예상 결과 번역
    if case_data.get('expected_result'):
        translated['expected_result'] = translate_text(
            case_data['expected_result'],
            source_lang,
            target_lang
        )
    
    return translated


def translate_cases_batch(cases_data, source_lang, target_lang):
    """
    여러 케이스를 일괄 번역합니다 (한 번의 API 요청으로 처리).
    
    Args:
        cases_data: 케이스 데이터 리스트 [{'case_id': 1, 'title': '...', 'steps': '...', 'expected_result': '...'}, ...]
        source_lang: 원본 언어
        target_lang: 대상 언어
    
    Returns:
        번역된 케이스 데이터 리스트 [{'case_id': 1, 'translation': {...}}, ...]
    """
    if not cases_data:
        return []
    
    if source_lang == target_lang:
        return [{'case_id': case['case_id'], 'translation': case} for case in cases_data]
    
    # OpenAI 클라이언트 가져오기
    client = get_openai_client()
    if not client:
        error_msg = 'OpenAI API 키가 설정되지 않았습니다. 관리자에게 문의하세요.'
        logger.error(error_msg)
        raise TranslationError(error_msg)
    
    try:
        lang_names = {
            'ko': 'Korean',
            'en': 'English'
        }
        
        # 활성 프롬프트 가져오기
        prompt_config = get_active_prompt()
        
        # 모든 케이스를 JSON 형태로 묶어서 한 번에 번역 요청
        import json
        cases_json = []
        for case in cases_data:
            cases_json.append({
                'id': case['case_id'],
                'title': case.get('title', ''),
                'steps': case.get('steps', ''),
                'expected_result': case.get('expected_result', '')
            })
        
        # 사용자 프롬프트 생성
        user_prompt = f"""Translate the following test cases from {lang_names[source_lang]} to {lang_names[target_lang]}.
Keep the same JSON structure and formatting. Only provide the translated JSON, no explanations.

{prompt_config['system_prompt']}

Test cases to translate:
{json.dumps(cases_json, ensure_ascii=False, indent=2)}

Return the translated test cases in the same JSON format."""
        
        # 사용할 모델 결정
        model = prompt_config.get('model', 'gpt-4o-mini')
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a professional translator specializing in software testing documentation. Always return valid JSON."},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=8000
        )
        
        translated_text = response.choices[0].message.content.strip()
        
        # JSON 추출 (```json ... ``` 형태로 올 수 있음)
        if '```json' in translated_text:
            translated_text = translated_text.split('```json')[1].split('```')[0].strip()
        elif '```' in translated_text:
            translated_text = translated_text.split('```')[1].split('```')[0].strip()
        
        # JSON 파싱
        translated_cases_json = json.loads(translated_text)
        
        # 결과 매핑
        result = []
        for translated_case in translated_cases_json:
            result.append({
                'case_id': translated_case['id'],
                'translation': {
                    'title': translated_case.get('title', ''),
                    'steps': translated_case.get('steps', ''),
                    'expected_result': translated_case.get('expected_result', '')
                }
            })
        
        # 사용량 기록
        try:
            from app.models import TranslationUsage
            from app import db
            from flask import has_request_context
            from flask_login import current_user
            from app.utils.model_pricing import calculate_cost
            
            usage = response.usage
            input_tokens = usage.prompt_tokens if hasattr(usage, 'prompt_tokens') else 0
            output_tokens = usage.completion_tokens if hasattr(usage, 'completion_tokens') else 0
            total_tokens = usage.total_tokens if hasattr(usage, 'total_tokens') else 0
            
            # 모델별 가격 계산
            cost = calculate_cost(model, input_tokens, output_tokens)
            
            usage_record = TranslationUsage(
                source_lang=source_lang,
                target_lang=target_lang,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                model=model,
                cost=cost,
                user_id=current_user.id if has_request_context() and current_user.is_authenticated else None
            )
            db.session.add(usage_record)
            db.session.commit()
            
            logger.info(f'배치 번역 완료: {len(cases_data)}개 케이스, {source_lang} -> {target_lang} (모델: {model}, {total_tokens} tokens, ${cost:.6f})')
        except Exception as e:
            logger.warning(f'사용량 기록 실패: {e}')
        
        return result
        
    except json.JSONDecodeError as e:
        error_msg = f'번역 결과 파싱 실패: {str(e)}'
        logger.error(error_msg)
        raise TranslationError(f'번역 결과를 처리할 수 없습니다: {str(e)}')
    except Exception as e:
        error_msg = f'배치 번역 실패: {str(e)}'
        logger.error(error_msg)
        
        # OpenAI API 관련 에러 메시지 개선
        if 'authentication' in str(e).lower() or 'api_key' in str(e).lower():
            raise TranslationError('OpenAI API 키가 유효하지 않습니다. 관리자에게 문의하세요.')
        elif 'rate_limit' in str(e).lower():
            raise TranslationError('OpenAI API 사용량 한도를 초과했습니다. 잠시 후 다시 시도하세요.')
        elif 'insufficient_quota' in str(e).lower():
            raise TranslationError('OpenAI API 크레딧이 부족합니다. 관리자에게 문의하세요.')
        else:
            raise TranslationError(f'번역 중 오류가 발생했습니다: {str(e)}')

