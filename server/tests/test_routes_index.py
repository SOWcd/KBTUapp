from fastapi.routing import APIRoute

from helpers import env  # noqa: F401
from tools.routes import routes


def test_routes_index_lists_every_route(env):  # noqa: F811
    """tools/routes.py reads app.py's source; it must find every route the running app serves, at the line it says."""
    client, _ = env
    served = {(m, r.path) for r in client.app.routes if isinstance(r, APIRoute) for m in r.methods if m != "HEAD"}
    listed = {(m, p) for m, p, *_ in routes()}
    assert listed == served
