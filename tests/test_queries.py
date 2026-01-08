from pihole_sqlite_exporter import queries


def test_blocked_queries_use_blocked_list_placeholder() -> None:
    assert "{blocked_list}" in queries.SQL_BLOCKED_TODAY
    assert "{blocked_list}" in queries.SQL_LIFETIME_BLOCKED
    assert "{blocked_list}" in queries.SQL_TOP_ADS


def test_top_queries_has_limit_placeholder() -> None:
    assert "{top_n}" in queries.SQL_TOP_QUERIES
    assert "{top_n}" in queries.SQL_TOP_ADS
