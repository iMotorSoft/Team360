"""Explicit pytest plugin: no network, native HANA driver, or shared writes."""
import socket
import sys
from types import ModuleType


def forbidden(*args, **kwargs):
    raise AssertionError('OFFLINE_GUARD: network/HANA access forbidden')


def pytest_sessionstart(session):
    from .run import install_offline_guard
    install_offline_guard()
    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden
    socket.create_connection = forbidden
    driver = ModuleType('hdbcli')
    api = ModuleType('hdbcli.dbapi')
    api.connect = forbidden
    driver.dbapi = api
    sys.modules['hdbcli'] = driver
    sys.modules['hdbcli.dbapi'] = api
