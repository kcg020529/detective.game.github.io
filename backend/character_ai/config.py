"""YB별 응답 모델 선택 예시.

팀에서 모델을 확정하기 전의 초안이다. 현재 service.py는 이 설정으로
외부 API를 호출하지 않는다. API 키는 이 파일이 아닌 환경변수에 둔다.
"""

CHARACTER_MODELS = {
    "YB-1": {"provider": "deepseek", "model": "deepseek-flash"},
    "YB-2": {"provider": "deepseek", "model": "deepseek-flash"},
    "YB-3": {"provider": "deepseek", "model": "deepseek-flash"},
    "YB-4": {"provider": "deepseek", "model": "deepseek-flash"},
    "YB-5": {"provider": "deepseek", "model": "deepseek-flash"},
    "YB-6": {"provider": "deepseek", "model": "deepseek-flash"},
}
