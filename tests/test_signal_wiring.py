from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings

from ftn_audit.apps import FtnAuditConfig
from ftn_audit.generic_formatters import GenericUpdateFormatter
from ftn_audit.constants import (
    DISPATCH_UID_M2M_CHANGED,
    DISPATCH_UID_POST_DELETE,
    DISPATCH_UID_POST_SAVE,
    DISPATCH_UID_PRE_SAVE,
)
from ftn_audit.m2m_receiver import _m2m_changed_receiver, connect_m2m_signals
from ftn_audit.receiver import (
    _post_delete_receiver,
    _post_save_receiver,
    _pre_save_receiver,
    connect_signals,
)
from ftn_audit.registry import AuditFormattersRegistry


def test_connect_signals_wires_all_model_signal_receivers():
    with patch("ftn_audit.receiver.pre_save.connect") as pre_connect:
        with patch("ftn_audit.receiver.post_save.connect") as post_connect:
            with patch("ftn_audit.receiver.post_delete.connect") as delete_connect:
                connect_signals()

    pre_connect.assert_called_once_with(
        _pre_save_receiver,
        dispatch_uid=DISPATCH_UID_PRE_SAVE,
    )
    post_connect.assert_called_once_with(
        _post_save_receiver,
        dispatch_uid=DISPATCH_UID_POST_SAVE,
    )
    delete_connect.assert_called_once_with(
        _post_delete_receiver,
        dispatch_uid=DISPATCH_UID_POST_DELETE,
    )


def test_connect_m2m_signals_wires_m2m_receiver():
    with patch("ftn_audit.m2m_receiver.m2m_changed.connect") as connect_mock:
        connect_m2m_signals()

    connect_mock.assert_called_once_with(
        _m2m_changed_receiver,
        dispatch_uid=DISPATCH_UID_M2M_CHANGED,
    )


@override_settings(
    AUDIT_AUTO_CONNECT_SIGNALS=False,
    AUDIT_AUTO_DISCOVER_FORMATTERS=False,
)
def test_app_ready_is_scoped_by_default():
    app_config = FtnAuditConfig("ftn_audit", __import__("ftn_audit"))
    with patch("ftn_audit.receiver.connect_signals") as connect_signals_mock:
        with patch("ftn_audit.m2m_receiver.connect_m2m_signals") as connect_m2m_signals_mock:
            with patch("ftn_audit.autodiscover.autodiscover_formatters") as autodiscover_mock:
                app_config.ready()

    connect_signals_mock.assert_not_called()
    connect_m2m_signals_mock.assert_not_called()
    autodiscover_mock.assert_not_called()


@override_settings(
    AUDIT_AUTO_CONNECT_SIGNALS=False,
    AUDIT_AUTO_DISCOVER_FORMATTERS=True,
)
def test_app_ready_loads_formatter_registrations():
    class _StartupModel:
        __name__ = "StartupModel"

    class _StartupFormatter(GenericUpdateFormatter):
        pass

    AuditFormattersRegistry.reset()
    app_config = FtnAuditConfig("ftn_audit", __import__("ftn_audit"))

    def _fake_autodiscover():
        AuditFormattersRegistry.register(_StartupModel, _StartupFormatter)

    with patch("ftn_audit.autodiscover.autodiscover_formatters", side_effect=_fake_autodiscover):
        app_config.ready()

    assert AuditFormattersRegistry.has_model(_StartupModel)
    resolved = AuditFormattersRegistry.find(_StartupModel, raw_route="PATCH|/v1/x/:id/", event_type="update")
    assert resolved is _StartupFormatter
    AuditFormattersRegistry.reset()
