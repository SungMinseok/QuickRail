#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""기본 요약 프롬프트 생성 스크립트"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

from app import create_app, db
from app.models import SummaryPrompt, User

app = create_app()

with app.app_context():
    # 기본 사용자 찾기 (admin@pubg.com 또는 첫 번째 admin)
    admin_user = User.query.filter(
        (User.email == 'admin@pubg.com') | (User.role == 'admin')
    ).first()
    
    if not admin_user:
        print("❌ Admin 사용자를 찾을 수 없습니다.")
        sys.exit(1)
    
    # 기존 sms-style 프롬프트 확인
    existing = SummaryPrompt.query.filter_by(name='sms-style').first()
    if existing:
        print("✅ 'sms-style' 프롬프트가 이미 존재합니다.")
        sys.exit(0)
    
    # 기본 요약 프롬프트 생성
    prompt = SummaryPrompt(
        name='sms-style',
        system_prompt='You are a professional QA engineer summarizing test run results. Generate concise summaries in SMS-style format.',
        user_prompt_template='''[환경]
- 빌드: {build_label}
- 백엔드: {backend_info}

[주요확인내역]
{test_results}

[참고사항]
{notes}''',
        model='gpt-4o-mini',
        is_active=True,  # 기본 활성화
        created_by=admin_user.id,
        updated_by=admin_user.id
    )
    
    # 기존 활성 프롬프트 비활성화
    SummaryPrompt.query.filter_by(is_active=True).update({'is_active': False})
    
    db.session.add(prompt)
    db.session.commit()
    
    print(f"✅ 기본 요약 프롬프트 'sms-style' 생성 완료!")
    print(f"   모델: {prompt.model}")
    print(f"   활성화: {prompt.is_active}")


