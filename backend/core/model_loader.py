"""从 configs/model.yaml 加载模型配置，返回 agno Model 实例。"""

import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import httpx
import yaml
from loguru import logger

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "model.yaml"


def load_model_config(config_path: Path = _CONFIG_PATH) -> Dict[str, Any]:
    """读取 model.yaml 并返回字典。"""
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    logger.info(f"模型配置加载成功: provider={cfg.get('provider')}, model={cfg.get('model')}")
    return cfg


def _build_http_client(config: Dict[str, Any]) -> Optional[httpx.AsyncClient]:
    """根据 model.yaml 的 SSL / 代理配置构造自定义 httpx.AsyncClient。

    触发条件（任一满足时返回自定义 client，否则返回 None 让 agno 使用默认 client）：
    - `verify_ssl: false` — 禁用 SSL 证书验证（企业 TLS 拦截 / 自签证书环境常见）
    - `ca_bundle: <path>` — 指向自定义 CA 证书文件
    - `proxy: <url>` — 配置 HTTP/HTTPS 代理
    - `trust_env: false` — 忽略环境变量里的代理配置

    默认行为（以上字段都未设置时）保持和原来完全一致：返回 None，agno 自己建 client。
    """
    verify_ssl = config.get("verify_ssl", True)
    ca_bundle = config.get("ca_bundle") or None
    proxy = config.get("proxy") or None
    trust_env = config.get("trust_env", True)
    timeout = config.get("timeout", 60)

    # 无任何自定义 → 返回 None，走 agno 默认 client
    if verify_ssl is True and not ca_bundle and not proxy and trust_env is True:
        return None

    # verify 参数：优先 ca_bundle（显式信任文件）→ 其次 verify_ssl（布尔）
    if ca_bundle:
        verify_arg: Any = ca_bundle
    else:
        verify_arg = bool(verify_ssl)

    client = httpx.AsyncClient(
        verify=verify_arg,
        proxy=proxy,
        trust_env=trust_env,
        timeout=timeout,
    )

    logger.warning(
        "model_loader: 使用自定义 httpx.AsyncClient — "
        f"verify={verify_arg!r}, proxy={proxy!r}, trust_env={trust_env}"
    )
    if verify_arg is False:
        logger.warning(
            "model_loader: SSL 证书验证已禁用（verify_ssl=false）。"
            "仅适用于企业内网 TLS 拦截 / 自签证书场景，生产环境请使用 ca_bundle 指向真实证书。"
        )
    return client


def create_model(config: Dict[str, Any] = None):
    """根据配置创建 agno Model 实例。

    Returns:
        agno Model 实例 (OpenAIChat / OpenAILike / OpenRouter)
    """
    if config is None:
        config = load_model_config()

    provider = config.get("provider", "openai")
    # 优先使用 yaml 中直接配置的 api_key，其次从环境变量读取
    api_key = config.get("api_key", "") or ""
    if not api_key:
        api_key_env = config.get("api_key_env", "OPENAI_API_KEY")
        api_key = os.environ.get(api_key_env, "")

    common_params: Dict[str, Any] = {
        "id": config.get("model", "gpt-4o-mini"),
        "api_key": api_key or None,
        "temperature": config.get("temperature", 0.3),
        "max_tokens": config.get("max_tokens", 4096),
        "timeout": config.get("timeout", 60),
    }

    # 自定义 role_map（用于不支持 developer 角色的 OpenAI 兼容 API）
    role_map = config.get("role_map")

    # 自定义 httpx.AsyncClient（SSL / 代理 / CA bundle）
    http_client = _build_http_client(config)
    if http_client is not None:
        common_params["http_client"] = http_client

    if provider == "openrouter":
        from agno.models.openrouter import OpenRouter

        params = {
            **common_params,
            "base_url": config.get("base_url", "https://openrouter.ai/api/v1"),
        }
        if role_map:
            params["role_map"] = role_map
        model = OpenRouter(**params)
    elif provider == "openai":
        from agno.models.openai import OpenAIChat

        params = {**common_params}
        base_url = config.get("base_url")
        if base_url:
            params["base_url"] = base_url
        if role_map:
            params["role_map"] = role_map
        model = OpenAIChat(**params)
    elif provider == "openai_like":
        from agno.models.openai.like import OpenAILike

        params = {**common_params, "base_url": config.get("base_url", "")}
        if role_map:
            params["role_map"] = role_map
        model = OpenAILike(**params)
    else:
        # 通用 OpenAI 兼容
        from agno.models.openai.like import OpenAILike

        params = {**common_params, "base_url": config.get("base_url", "")}
        if role_map:
            params["role_map"] = role_map
        model = OpenAILike(**params)

    logger.info(f"模型创建成功: {provider} / {common_params['id']}")
    return model


def inject_prompt_tracer(model, prompt_callback: Callable[..., None], agent_name: str = "") -> None:
    """向已创建的 model 注入 prompt 追踪回调。

    使用 monkey-patch 方式重写 ainvoke_stream，在调用上游 API 前触发回调，
    记录完整的 messages + tools + tool_choice，不影响原有流式逻辑。

    Args:
        model: agno Model 实例
        prompt_callback: 回调函数，签名 (messages, *, tools, tool_choice, agent_name)
        agent_name: 该 model 所属的 agent 名称，用于 trace 区分来源
    """
    import types

    original_ainvoke_stream = model.__class__.ainvoke_stream

    async def _traced_ainvoke_stream(self, messages, *args, **kwargs):
        try:
            # ainvoke_stream 签名: (messages, assistant_message, response_format, tools, tool_choice, ...)
            # tools/tool_choice 可能作为关键字或位置参数（偏移 +2/+3，因为 messages 已单独捕获）
            tools = kwargs.get("tools") or (args[2] if len(args) >= 3 else None)
            tool_choice = kwargs.get("tool_choice") or (args[3] if len(args) >= 4 else None)
            prompt_callback(messages, tools=tools, tool_choice=tool_choice, agent_name=agent_name)
        except Exception:
            pass  # trace 失败不影响主流程
        async for chunk in original_ainvoke_stream(self, messages, *args, **kwargs):
            yield chunk

    # 仅修改当前实例，不影响其他实例
    model.ainvoke_stream = types.MethodType(_traced_ainvoke_stream, model)
