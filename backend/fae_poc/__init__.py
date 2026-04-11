"""Fae POC 客户端封装 — 共享 NCELogin + config.ini 解析。

本包存放真实 FAE 平台的接入基础设施，被 `skills/remote_optimization` 等
真实接口调用型 Skill 共享：

- NCELogin.py        业务登录/接口类（用户本地提供，.gitignore 忽略）
- config.ini         真实凭证（用户本地提供，.gitignore 忽略）
- config.ini.example 占位模板（提交到仓库）

为什么放在项目根而不是 configs/：NCELogin.py 是 Python 模块，需要被
Skill 脚本 import；config.ini 又被 NCELogin.py 按相对路径读取，两者必
须同目录共存。放在 configs/ 会破坏这种耦合；放进 skills/<skill>/references/
会被 agno LocalSkills 扫描进 LLM 上下文。因此独立成项目根的 Python 包。

初次部署：
    1. 把本地 Fae POC 项目的 NCELogin.py 拷贝到本目录
    2. 把 config.ini.example 复制为 config.ini,填入真实 base_url /
       csrf_token / cookie
    3. 两个文件都已在 .gitignore 中排除,不会误提交

使用方式 (在 Skill 脚本顶部,skills/<skill>/scripts/xxx.py 距项目根 3 级)::

    import sys
    from pathlib import Path

    # 两条路径都注入 sys.path,以兼容两种 NCELogin 导入风格
    _PROJECT_ROOT = Path(__file__).resolve().parents[3]
    _FAE_POC_DIR = _PROJECT_ROOT / "fae_poc"
    for _p in (str(_PROJECT_ROOT), str(_FAE_POC_DIR)):
        if _p not in sys.path:
            sys.path.insert(0, _p)

    from fae_poc import DEFAULT_CONFIG_PATH, require_config  # 辅助 (无 NCELogin 也不报错)

    def main():
        args = parse_args()
        config_path = require_config(args.config)   # 校验并返回绝对路径
        from NCELogin import NCELogin                # bare 导入,延迟执行,便于失败降级
        nce_login = NCELogin(config_file=str(config_path))
        ...

**两种 NCELogin 导入风格均被支持** (sys.path 里同时有项目根 + fae_poc 目录)::

    # 风格 A: 通过 fae_poc 包 (适合新写的脚本)
    from fae_poc import NCELogin           # via __init__.py 的 `from .NCELogin import NCELogin`

    # 风格 B: bare 导入 (适合从本地 "Fae POC" 项目原样迁移过来的脚本)
    from NCELogin import NCELogin          # NCELogin.py 位于 fae_poc/ 目录,已在 sys.path 上

`DEFAULT_CONFIG_PATH` 指向 `fae_poc/config.ini` 的绝对路径,Skill 脚本的
argparse `--config` 参数默认值必须使用它 (否则相对路径 `../../config.ini`
会因为 CWD 不同而解析错位)。

NCELogin 采用**延迟导入**：如果 `NCELogin.py` 尚未被用户放入本目录
（例如 CI 环境或新 clone 未完成部署），`import fae_poc` 本身不会报错，
仅 `NCELogin` 变量为 None，具体报错通过 `require_ncelogin()` 延迟到真正
使用时抛出，并附带引导信息。
"""

from pathlib import Path
from typing import Any, Optional

_PACKAGE_DIR = Path(__file__).resolve().parent

# 默认 config.ini 绝对路径 — 各 Skill 脚本的 --config 参数默认值
DEFAULT_CONFIG_PATH: Path = _PACKAGE_DIR / "config.ini"

# 例子模板路径 — 用户首次部署时可 cp example → config.ini
EXAMPLE_CONFIG_PATH: Path = _PACKAGE_DIR / "config.ini.example"

# 延迟导入 NCELogin
NCELogin: Optional[Any] = None
_ncelogin_import_error: Optional[BaseException] = None

try:
    from .NCELogin import NCELogin  # type: ignore  # noqa: F401
except ImportError as exc:
    _ncelogin_import_error = exc


def require_ncelogin() -> Any:
    """显式校验 NCELogin 已就位。

    在 Skill 脚本的 main() 入口调用，失败时抛出清晰错误引导用户部署。
    """
    if NCELogin is None:
        raise RuntimeError(
            "fae_poc.NCELogin 尚未部署。请将本地的 NCELogin.py 放到 "
            f"{_PACKAGE_DIR / 'NCELogin.py'}，并确保 config.ini 已准备好"
            f"（参考 {EXAMPLE_CONFIG_PATH}）。"
            f"\n原始导入错误: {_ncelogin_import_error!r}"
        )
    return NCELogin


def require_config(config_path: Optional[Path] = None) -> Path:
    """显式校验 config.ini 存在并返回其绝对路径。

    Args:
        config_path: 用户显式指定的 config 路径；None 则使用 DEFAULT_CONFIG_PATH

    Returns:
        存在的 config.ini 绝对路径
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(
            f"config.ini 不存在: {path}\n"
            f"请参考 {EXAMPLE_CONFIG_PATH} 创建，并填入真实 base_url / csrf_token / cookie。"
        )
    return path


__all__ = [
    "NCELogin",
    "DEFAULT_CONFIG_PATH",
    "EXAMPLE_CONFIG_PATH",
    "require_ncelogin",
    "require_config",
]
