"""路由命名空间收口：本地单进程把接口挪到 /api，生产拓扑保持根路径。

背景：本进程同时托管前端之后，`/holdings` `/transactions` `/deposits` 这些
既是前端 history 路由、又是接口路径，请求会命中接口、返回裸 JSON。收口后
两种拓扑各自成立，且生产（Docker/VPS）拓扑与改造前逐字一致。
"""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

# frontend/src/modules/tabNav.js 里 ROUTE_META 去掉 REDIRECT_ONLY 后的 12 个页签
PAGE_PATHS = [
    "/",
    "/holdings",
    "/transactions",
    "/broker",
    "/deposits",
    "/cash",
    "/decision",
    "/performance",
    "/allocation",
    "/ops/notify",
    "/ops/ai",
    "/ops/backup",
]

# 收口前与页签路径撞车的三个接口
COLLIDING_API_PATHS = ["/api/holdings", "/api/transactions", "/api/deposits"]


def has_strip_middleware(module):
    """模块对应的 app 上是否挂着剥 /api 前缀的中间件。"""
    cls = module.StripApiPrefixMiddleware
    return any(getattr(m, "cls", None) is cls for m in module.app.user_middleware)


def test_vps_topology_keeps_root_paths(app_module):
    """没有 dist（Docker/VPS、pytest）：接口在根路径，中间件照挂。"""
    assert app_module.SERVE_FRONTEND is False
    assert app_module.API_PREFIX == ""
    assert has_strip_middleware(app_module) is True


def test_single_process_topology_moves_api_under_prefix(spa_app):
    """有 dist（本机直接运行）：接口统一在 /api 下，不再剥前缀。"""
    assert spa_app.SERVE_FRONTEND is True
    assert spa_app.API_PREFIX == "/api"
    assert has_strip_middleware(spa_app) is False


@pytest.mark.parametrize("path", PAGE_PATHS)
def test_page_paths_return_html_in_single_process(spa_app, path):
    """12 个页签路径刷新 / 深链都出页面，不是裸 JSON。"""
    response = TestClient(spa_app.app).get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "spa-index" in response.text


@pytest.mark.parametrize("path", COLLIDING_API_PATHS)
def test_colliding_api_paths_return_json_in_single_process(spa_app, path):
    """前端请求走的 /api/* 仍然拿到 JSON。"""
    response = TestClient(spa_app.app).get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("path", ["/holdings", "/transactions", "/deposits"])
def test_root_paths_stay_api_when_not_serving_frontend(client, path):
    """生产拓扑下这些路径仍是接口——改动不许影响 VPS。"""
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


def test_unknown_api_path_is_404_json_in_single_process(spa_app):
    """中间件确实没挂：/api/* 不会先被剥成 /* 再回落成首页。"""
    response = TestClient(spa_app.app).get("/api/definitely-not-a-route")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_unknown_page_path_falls_back_to_index_in_single_process(spa_app):
    response = TestClient(spa_app.app).get("/not-a-page")
    assert response.status_code == 200
    assert "spa-index" in response.text


@pytest.mark.parametrize("path", ["/health", "/api/health"])
def test_health_answers_in_both_namespaces(spa_app, path):
    """/health 直连（Docker healthcheck）与 /api/health（前端、nginx）都要通。"""
    response = TestClient(spa_app.app).get(path)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
