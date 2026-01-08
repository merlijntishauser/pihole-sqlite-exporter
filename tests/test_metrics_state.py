from pihole_sqlite_exporter.metrics_state import MetricsState


def test_metrics_state_defaults() -> None:
    state = MetricsState()
    assert state.total_queries_lifetime == 0
    assert state.blocked_queries_lifetime == 0
