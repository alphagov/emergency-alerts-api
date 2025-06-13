def test_sql_statement_timeout(notify_db_session):
    timeout = notify_db_session.execute("show statement_timeout").scalar()
    assert timeout == "20min"


def test_sql_application_name(notify_db_session):
    name = notify_db_session.execute("show application_name").one()
    assert name[0] == "test"
