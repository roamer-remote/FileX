# Copyright (c) 2026 徐泽宇
"""按 IP 的进程内滑动窗口限速（login/register/license activate 等）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import threading
import time

from fastapi import HTTPException, Request, status

logger = logging.getLogger("filex.rate_limit")


class IpRateLimiter:
    """简单内存限速器；单进程有效，测试可 reset_for_tests。"""

    def __init__(self, *, limit: int, window_sec: float, detail: str) -> None:
        self.limit = limit
        self.window_sec = window_sec
        self.detail = detail
        self._lock = threading.Lock()
        self._attempts: dict[str, list[float]] = {}

    @staticmethod
    def client_ip(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def check(self, ip: str) -> None:
        now = time.time()
        with self._lock:
            attempts = [t for t in self._attempts.get(ip, []) if now - t < self.window_sec]
            if not attempts:
                self._attempts.pop(ip, None)
            if len(attempts) >= self.limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=self.detail,
                )
            attempts.append(now)
            self._attempts[ip] = attempts

    def reset_for_tests(self) -> None:
        with self._lock:
            self._attempts.clear()


def _redis_client():
    from config import REDIS_URL

    if not REDIS_URL:
        return None
    import redis

    return redis.from_url(REDIS_URL, decode_responses=True)


class RedisIpRateLimiter:
    """Redis 固定窗口限速；不可用时回退进程内 IpRateLimiter。"""

    def __init__(
        self,
        *,
        key_prefix: str,
        limit: int,
        window_sec: float,
        detail: str,
    ) -> None:
        self.key_prefix = key_prefix
        self.limit = limit
        self.window_sec = max(1, int(window_sec))
        self.detail = detail
        self._fallback = IpRateLimiter(limit=limit, window_sec=window_sec, detail=detail)

    def check(self, ip: str) -> None:
        client = _redis_client()
        if client is None:
            self._fallback.check(ip)
            return
        key = f"{self.key_prefix}:{ip}"
        try:
            count = int(client.incr(key))
            if count == 1:
                client.expire(key, self.window_sec)
            elif client.ttl(key) == -1:
                client.expire(key, self.window_sec)
            if count > self.limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=self.detail,
                )
        except HTTPException:
            raise
        except Exception:
            logger.exception("redis rate limit failed key=%s, fallback to memory", key)
            self._fallback.check(ip)

    def reset_for_tests(self) -> None:
        self._fallback.reset_for_tests()


AUTH_LOGIN_RATE_LIMITER = IpRateLimiter(
    limit=5,
    window_sec=60.0,
    detail="登录请求过于频繁，请稍后再试",
)
AUTH_REGISTER_RATE_LIMITER = IpRateLimiter(
    limit=5,
    window_sec=60.0,
    detail="注册请求过于频繁，请稍后再试",
)
LICENSE_ACTIVATE_RATE_LIMITER = RedisIpRateLimiter(
    key_prefix="filex:rate:license_activate",
    limit=5,
    window_sec=60.0,
    detail="激活请求过于频繁，请稍后再试",
)
