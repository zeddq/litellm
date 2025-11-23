[project]
name = "litellm-proxy"
version = "0.1.0"
description = "LiteLLM Proxy with PostgreSQL"
authors = [
    {name = "Cezary Marczak",email = "cezary@procyon.ai"}
]
readme = "README.md"
requires-python = "^3.13"
dependencies = [
    "litellm[proxy] (>=1.79.0,<2.0.0)",
    "prisma (>=0.15.0,<0.16.0)",
    "litellm-types (>=0.0.16,<0.0.17)"
]

[project.scripts]
run-proxies = "run_proxies:run_proxies"

[build-system]
requires = ["poetry-core>=2.0.0,<3.0.0"]
build-backend = "poetry.core.masonry.api"
