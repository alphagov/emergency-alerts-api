def test_postgis_extension_added_to_db(
    notify_db_session,
):
    result = notify_db_session.execute("SELECT extname FROM pg_extension WHERE extname='postgis'").one()
    assert result is not None
    assert result[0] == "postgis"
