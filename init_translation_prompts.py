"""
번역 프롬프트 초기화 스크립트
기본 프롬프트를 데이터베이스에 추가합니다.
"""
from app import create_app, db
from app.models import TranslationPrompt

def init_prompts():
    app = create_app()
    
    with app.app_context():
        # 기존 프롬프트 확인
        existing = TranslationPrompt.query.filter_by(name='default').first()
        if existing:
            print('기본 프롬프트가 이미 존재합니다.')
            return
        
        # 기본 프롬프트 생성
        default_prompt = TranslationPrompt(
            name='default',
            system_prompt='You are a professional translator specializing in software testing documentation.',
            user_prompt_template='Translate the following text from {source_lang} to {target_lang}.\nKeep the same formatting and structure. Only provide the translation, no explanations.\n\nText to translate:\n{text}',
            is_active=True
        )
        
        db.session.add(default_prompt)
        
        # 예시: Check if 로 시작하는 프롬프트
        check_if_prompt = TranslationPrompt(
            name='check-if-style',
            system_prompt='You are a professional translator specializing in software testing documentation. All test case titles must start with "Check if" in English.',
            user_prompt_template='Translate the following text from {source_lang} to {target_lang}.\nKeep the same formatting and structure. Only provide the translation, no explanations.\n\nIMPORTANT RULES:\n- If translating to English, all test case titles MUST start with "Check if"\n- Maintain the original meaning while following this format\n\nText to translate:\n{text}',
            is_active=False
        )
        
        db.session.add(check_if_prompt)
        
        db.session.commit()
        
        print('[OK] 기본 프롬프트가 생성되었습니다.')
        print('  - default (활성)')
        print('  - check-if-style (비활성)')
        print('')
        print('설정 페이지에서 프롬프트를 관리할 수 있습니다.')

if __name__ == '__main__':
    init_prompts()

