"""The last, partially filled page must exist and be reachable."""

import pytest

from conftest import ids


@pytest.mark.parametrize("page_size,pages", [(4, 3), (2, 5), (5, 2), (8, 2)])
def test_total_pages_rounds_up(client, page_size, pages):
    assert client.get("/orders", params={"page_size": page_size}).json()["total_pages"] == pages


@pytest.mark.parametrize("page_size,page", [(4, 3), (2, 5), (5, 2)])
def test_last_partial_page_reachable(client, page_size, page):
    r = client.get("/orders", params={"page": page, "page_size": page_size})
    assert r.status_code == 200
    assert ids(r)[-1] == 9
