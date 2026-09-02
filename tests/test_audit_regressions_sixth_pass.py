# -*- coding: utf-8 -*-
"""第六轮审计回归：P1 数据可靠性 + 安全。

8.  K 线写入路径 NaN 未过滤（产出非法 JSON）
14. 通知 webhook 无 SSRF 防护
9.  akshare 无超时兜底（socket.setdefaulttimeout 已设）
"""
import socket

from kline_cache import _fnum
from notify import validate_webhook_url


# ----------------------------- bug 8 -----------------------------

def test_fnum_filters_nonfinite():
    assert _fnum(3.5) == 3.5
    assert _fnum(float("nan")) == 0.0
    assert _fnum(float("inf")) == 0.0
    assert _fnum(float("-inf")) == 0.0
    assert _fnum(None) == 0.0
    assert _fnum("") == 0.0
    assert _fnum("nan") == 0.0
    # 默认回退可覆盖
    assert _fnum(float("nan"), default=-1.0) == -1.0


# ----------------------------- bug 14 -----------------------------

def test_webhook_validation_rejects_ssrf_targets():
    assert validate_webhook_url("ftp://93.184.216.34/hook") is not None      # 非法 scheme
    assert validate_webhook_url("http://127.0.0.1/hook") is not None         # 环回
    assert validate_webhook_url("http://169.254.169.254/latest/meta-data") is not None  # 元数据
    assert validate_webhook_url("http://10.1.2.3/hook") is not None          # 内网
    assert validate_webhook_url("http://192.168.0.1/hook") is not None       # 内网
    assert validate_webhook_url("http://[::1]/hook") is not None             # IPv6 环回


def test_webhook_validation_allows_public_http():
    # 字面公网 IP 不触发 DNS，直接放行
    assert validate_webhook_url("https://93.184.216.34/hook") is None
    assert validate_webhook_url("http://93.184.216.34/hook") is None
    assert validate_webhook_url("") is not None


# ----------------------------- bug 9 -----------------------------

def test_socket_default_timeout_is_set():
    # database 模块导入时设置；这里任何 backend 模块 import 后都该生效
    t = socket.getdefaulttimeout()
    assert t is not None and t > 0