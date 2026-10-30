"""AI 表演提示词编译器 —— 把「情绪」编译成「可执行的表演」。"""

__version__ = "0.1.0"

from .au import AULibrary  # noqa: F401
from .compiler import compile_flat, compile_text  # noqa: F401
from .schema import load  # noqa: F401
