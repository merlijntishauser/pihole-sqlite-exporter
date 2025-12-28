BLOCKED_STATUSES = {1, 4, 5, 6, 7, 8, 9, 10, 11, 15}

QUERY_TYPE_MAP = {
    1: "A",
    2: "AAAA",
    3: "ANY",
    4: "SRV",
    5: "SOA",
    6: "PTR",
    7: "TXT",
    8: "NAPTR",
    9: "MX",
    10: "DS",
    11: "RRSIG",
    12: "DNSKEY",
    13: "NS",
    14: "OTHER",
    15: "SVCB",
    16: "HTTPS",
}

REPLY_TYPE_MAP = {
    0: "unknown",
    1: "no_data",
    2: "nx_domain",
    3: "cname",
    4: "ip",
    5: "domain",
    6: "rr_name",
    7: "serv_fail",
    8: "refused",
    9: "not_imp",
    10: "other",
    11: "dnssec",
    12: "none",
    13: "blob",
}
