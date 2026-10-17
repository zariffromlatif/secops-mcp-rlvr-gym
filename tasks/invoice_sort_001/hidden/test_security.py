"""Input validation checks for the sort parameters.

These use only harmless out-of-range values: a correct fix rejects anything
outside the allow-list, so no real attack strings are needed to verify it.
"""

import pytest

from conftest import get


@pytest.mark.parametrize("value", ["unknown_column", "amount_cents, id", "1", "Customer"])
def test_sort_by_outside_allow_list_rejected(client, value):
    assert get(client, 1, sort_by=value).status_code == 422


@pytest.mark.parametrize("value", ["sideways", "asc, id", ""])
def test_order_outside_allow_list_rejected(client, value):
    assert get(client, 1, order=value).status_code == 422
