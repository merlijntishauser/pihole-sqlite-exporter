SQL_COUNTER_TOTAL = "SELECT value FROM counters WHERE id = 0;"
SQL_COUNTER_BLOCKED = "SELECT value FROM counters WHERE id = 1;"
SQL_CLIENTS_EVER_SEEN = "SELECT COUNT(*) FROM client_by_id;"
SQL_DOMAIN_BY_ID_COUNT = "SELECT COUNT(*) FROM domain_by_id;"
SQL_GRAVITY_COUNT = "SELECT COUNT(*) FROM gravity;"

SQL_LIFETIME_FORWARD_DESTS = """
SELECT forward, COUNT(*)
FROM queries
WHERE status = 2
  AND forward IS NOT NULL
GROUP BY forward;
"""

SQL_LIFETIME_CACHE = "SELECT COUNT(*) FROM queries WHERE status = 3;"
SQL_LIFETIME_BLOCKED = "SELECT COUNT(*) FROM queries WHERE status IN ({blocked_list});"

SQL_QUERIES_TODAY = """
SELECT COUNT(*)
FROM queries
WHERE timestamp >= ?;
"""

SQL_BLOCKED_TODAY = """
SELECT COUNT(*)
FROM queries
WHERE timestamp >= ?
  AND status IN ({blocked_list});
"""

SQL_UNIQUE_CLIENTS = "SELECT COUNT(DISTINCT client) FROM queries WHERE timestamp >= ?;"
SQL_UNIQUE_DOMAINS = "SELECT COUNT(DISTINCT domain) FROM queries WHERE timestamp >= ?;"

SQL_QUERY_TYPES = """
SELECT type, COUNT(*) AS cnt
FROM queries
WHERE timestamp >= ?
GROUP BY type;
"""

SQL_REPLY_TYPES = """
SELECT reply_type, COUNT(*) AS cnt
FROM queries
WHERE timestamp >= ?
GROUP BY reply_type;
"""

SQL_FORWARDED_TODAY = "SELECT COUNT(*) FROM queries WHERE timestamp >= ? AND status = 2;"
SQL_CACHED_TODAY = "SELECT COUNT(*) FROM queries WHERE timestamp >= ? AND status = 3;"

SQL_FORWARD_DESTS_TODAY = """
SELECT forward, COUNT(*) AS cnt, AVG(reply_time) AS avg_rt
FROM queries
WHERE timestamp >= ?
  AND status = 2
  AND forward IS NOT NULL
GROUP BY forward;
"""

SQL_FORWARD_REPLY_TIMES = """
SELECT reply_time
FROM queries
WHERE timestamp >= ?
  AND status = 2
  AND forward = ?
  AND reply_time IS NOT NULL;
"""

SQL_TOP_ADS = """
SELECT domain, COUNT(*) AS cnt
FROM queries
WHERE timestamp >= ?
  AND status IN ({blocked_list})
GROUP BY domain
ORDER BY cnt DESC
LIMIT {top_n};
"""

SQL_TOP_QUERIES = """
SELECT domain, COUNT(*) AS cnt
FROM queries
WHERE timestamp >= ?
GROUP BY domain
ORDER BY cnt DESC
LIMIT {top_n};
"""

SQL_TOP_SOURCES = """
SELECT q.client, COALESCE(c.name,''), COUNT(*) AS cnt
FROM queries q
LEFT JOIN client_by_id c ON c.ip = q.client
WHERE q.timestamp >= ?
GROUP BY q.client, c.name
ORDER BY cnt DESC
LIMIT {top_n};
"""
