"""Shared application constants for Flask wiring."""

from collections import defaultdict


DEPARTMENT_DIRS = {"行政管理部", "人事部", "财务部", "场地部", "媒体部", "业务部", "综合服务部", "项目管理部"}
MAX_REQUEST_SIZE = 10 * 1024 * 1024
RATE_LIMITS = {
    "chat": 20,
    "agent_generate": 10,
    "api_login": 5,
}


def new_rate_limit_store():
    return defaultdict(list)
