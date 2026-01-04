"""
SMTM package

정석 원칙:
- __init__.py에서 무거운 import(판다스/DB/전략/트레이더/컨트롤러 등) 금지
- 필요한 클래스는 사용하는 파일에서 직접 import 한다.
"""

__version__ = "1.7.1"
__all__ = ["__version__"]
