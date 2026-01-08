"""
OpenAI 모델별 가격 정보 및 유틸리티
"""

# OpenAI 모델별 가격 정보 (USD per 1M tokens)
# 2024년 12월 기준
MODEL_PRICING = {
    'gpt-4o': {
        'name': 'GPT-4o',
        'input': 2.50,   # $2.50 / 1M tokens
        'output': 10.00,  # $10.00 / 1M tokens
        'description': '최신 GPT-4 모델, 높은 품질',
        'recommended': False
    },
    'gpt-4o-mini': {
        'name': 'GPT-4o Mini',
        'input': 0.150,   # $0.15 / 1M tokens
        'output': 0.600,  # $0.60 / 1M tokens
        'description': 'GPT-4 수준의 품질, 저렴한 가격 (추천)',
        'recommended': True
    },
    'gpt-4-turbo': {
        'name': 'GPT-4 Turbo',
        'input': 10.00,   # $10.00 / 1M tokens
        'output': 30.00,  # $30.00 / 1M tokens
        'description': 'GPT-4 Turbo, 매우 높은 품질',
        'recommended': False
    },
    'gpt-3.5-turbo': {
        'name': 'GPT-3.5 Turbo',
        'input': 0.50,    # $0.50 / 1M tokens
        'output': 1.50,   # $1.50 / 1M tokens
        'description': '빠르고 저렴한 모델',
        'recommended': False
    },
    'gpt-3.5-turbo-0125': {
        'name': 'GPT-3.5 Turbo (0125)',
        'input': 0.50,    # $0.50 / 1M tokens
        'output': 1.50,   # $1.50 / 1M tokens
        'description': 'GPT-3.5 최신 버전',
        'recommended': False
    }
}


def get_model_list():
    """사용 가능한 모델 목록 반환"""
    return [
        {
            'id': model_id,
            'name': info['name'],
            'description': info['description'],
            'input_price': info['input'],
            'output_price': info['output'],
            'recommended': info['recommended']
        }
        for model_id, info in MODEL_PRICING.items()
    ]


def get_model_info(model_id):
    """특정 모델의 정보 반환"""
    return MODEL_PRICING.get(model_id, MODEL_PRICING['gpt-3.5-turbo'])


def calculate_cost(model_id, input_tokens, output_tokens):
    """
    모델과 토큰 수를 기반으로 비용 계산
    
    Args:
        model_id: OpenAI 모델 ID
        input_tokens: 입력 토큰 수
        output_tokens: 출력 토큰 수
    
    Returns:
        float: 예상 비용 (USD)
    """
    pricing = get_model_info(model_id)
    
    # 1M tokens 기준 가격을 1 token 기준으로 변환
    input_cost = (input_tokens / 1_000_000) * pricing['input']
    output_cost = (output_tokens / 1_000_000) * pricing['output']
    
    return input_cost + output_cost


def get_cheapest_model():
    """가장 저렴한 모델 반환"""
    cheapest = min(
        MODEL_PRICING.items(),
        key=lambda x: x[1]['input'] + x[1]['output']
    )
    return cheapest[0]


def get_recommended_model():
    """추천 모델 반환"""
    for model_id, info in MODEL_PRICING.items():
        if info['recommended']:
            return model_id
    return 'gpt-4o-mini'


def format_price(price):
    """가격을 읽기 쉬운 형식으로 변환"""
    if price >= 1.0:
        return f"${price:.2f}"
    elif price >= 0.01:
        return f"${price:.3f}"
    else:
        return f"${price:.6f}"


