"""Exam mode + proctoring tests (Phase 16).

Covers: exam creation (password required, invite roster), the proctor WS
pipeline (validation, server-side scoring, host-only fan-out), the host's
report (present/absent, scores, event timeline) and its CSV download.
"""

from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app as fastapi_app
from app.models.invite import MeetingInvite
from app.models.meeting import Meeting
from app.models.proctor import PROCTOR_SIGNALS, ProctorEvent
from tests.test_ws import _connect_ready, _envelope, _register, _ws
from tests.ws_client import WsTestClient

EXAM_PASSWORD = "exam-secret-1"


async def _create_exam(
    client: AsyncClient,
    token: str,
    *,
    password: str = "exam-secret-1",
    invites: list[str] | None = None,
    proctoring: bool = True,
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/meetings",
        json={
            "title": "Final exam",
            "kind": "exam",
            "password": password,
            "waiting_room": True,
            "proctoring_enabled": proctoring,
            "invite_emails": invites or [],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


class TestCreateExam:
    async def test_exam_requires_password(self, client: AsyncClient) -> None:
        auth = await _register(client, "exam1@procto.dev", "Host")

        response = await client.post(
            "/api/v1/meetings",
            json={"kind": "exam"},
            headers={"Authorization": f"Bearer {auth['access_token']}"},
        )

        assert response.status_code == 422

    async def test_exam_is_flagged_and_proctored(self, client: AsyncClient) -> None:
        auth = await _register(client, "exam2@procto.dev", "Host")

        meeting = await _create_exam(client, auth["access_token"])

        assert meeting["kind"] == "exam"
        assert meeting["proctoring_enabled"] is True
        assert meeting["has_password"] is True
        assert meeting["waiting_room"] is True

    async def test_standard_meeting_never_proctored(self, client: AsyncClient) -> None:
        auth = await _register(client, "exam3@procto.dev", "Host")

        response = await client.post(
            "/api/v1/meetings",
            json={"proctoring_enabled": True},
            headers={"Authorization": f"Bearer {auth['access_token']}"},
        )

        data = response.json()
        assert data["kind"] == "standard"
        assert data["proctoring_enabled"] is False

    async def test_invite_roster_is_persisted(self, client: AsyncClient) -> None:
        auth = await _register(client, "exam4@procto.dev", "Host")

        meeting = await _create_exam(
            client,
            auth["access_token"],
            invites=["a@procto.dev", "b@procto.dev", "A@PROCTO.DEV"],
        )

        async with SessionLocal() as session:
            rows = (
                await session.scalars(
                    select(MeetingInvite).where(MeetingInvite.meeting_id == meeting["id"])
                )
            ).all()
        # Duplicate emails collapse case-insensitively (CITEXT).
        assert sorted(r.email.lower() for r in rows) == ["a@procto.dev", "b@procto.dev"]

    async def test_invalid_kind_is_rejected(self, client: AsyncClient) -> None:
        auth = await _register(client, "exam5@procto.dev", "Host")

        response = await client.post(
            "/api/v1/meetings",
            json={"kind": "webinar", "password": "exam-secret-1"},
            headers={"Authorization": f"Bearer {auth['access_token']}"},
        )

        assert response.status_code == 422


async def _join_exam_via_ws(
    client: AsyncClient, meeting: dict[str, Any], student: dict[str, Any]
) -> WsTestClient:
    """Connect a student to an exam room.

    Flips waiting_room off first (host approval is covered in
    test_host_controls; here we exercise the WS proctor pipeline) and passes
    the meeting password as a query param, as the pre-join flow does.
    """
    async with SessionLocal() as session:
        row = await session.get(Meeting, meeting["id"])
        assert row is not None
        row.waiting_room = False
        await session.commit()
    ws = WsTestClient(
        fastapi_app,
        f"/api/v1/ws/meetings/{meeting['code']}",
        query={"token": student["access_token"], "password": EXAM_PASSWORD},
    )
    await ws.connect()
    await ws.receive_type("sync.state")
    return ws


class TestProctorEvents:
    async def test_signal_is_scored_and_fanned_out_to_host(self, client: AsyncClient) -> None:
        host = await _register(client, "phost@procto.dev", "Host")
        student = await _register(client, "pstudent@procto.dev", "Student")
        meeting = await _create_exam(client, host["access_token"])

        ws_host = _ws(meeting["code"], host["access_token"])
        await _connect_ready(ws_host)
        ws_student = await _join_exam_via_ws(client, meeting, student)

        await ws_student.send(
            _envelope("proctor.event", {"signal": "looking_away", "duration_s": 3.2})
        )

        flag = await ws_host.receive_type("proctor.flag")
        payload = flag["payload"]
        assert payload["signal"] == "looking_away"
        assert payload["points"] == PROCTOR_SIGNALS["looking_away"] == 2
        assert payload["name"] == "Student"
        assert payload["minute"] >= 0

        async with SessionLocal() as session:
            events = (await session.scalars(select(ProctorEvent))).all()
        assert len(events) == 1
        assert str(events[0].user_id) == student["user"]["id"]
        assert events[0].points == 2

        await ws_host.close()
        await ws_student.close()

    async def test_student_never_sees_their_own_flag_fanout(self, client: AsyncClient) -> None:
        host = await _register(client, "ph2host@procto.dev", "Host")
        student = await _register(client, "ph2student@procto.dev", "Student")
        meeting = await _create_exam(client, host["access_token"])

        ws_student = await _join_exam_via_ws(client, meeting, student)
        await ws_student.send(_envelope("proctor.event", {"signal": "speaking", "duration_s": 1.0}))
        # The student's socket must NOT receive the flag (host-only fan-out).
        with pytest.raises(TimeoutError):
            await ws_student.receive_type("proctor.flag", timeout=0.4)
        await ws_student.close()

    async def test_chat_mentioning_frame_type_still_delivers(self, client: AsyncClient) -> None:
        """A chat body containing the literal `proctor.flag` text is ordinary
        chat: the host-only filter matches the parsed frame type, so the
        substring in a message body must not affect visibility."""
        student = await _register(client, "ph6student@procto.dev", "Student")
        other = await _register(client, "ph6other@procto.dev", "Other")
        meeting_response = await client.post(
            "/api/v1/meetings",
            json={"title": "Regular"},
            headers={"Authorization": f"Bearer {student['access_token']}"},
        )
        meeting = meeting_response.json()

        ws_a = _ws(meeting["code"], student["access_token"])
        await _connect_ready(ws_a)
        ws_b = _ws(meeting["code"], other["access_token"])
        await _connect_ready(ws_b)

        await ws_a.send(
            _envelope("chat.send", {"body": 'type "proctor.flag" here', "client_id": "c1"})
        )
        received = await ws_b.receive_type("chat.message")
        assert "proctor.flag" in received["payload"]["body"]

        await ws_a.close()
        await ws_b.close()

    async def test_invalid_signal_is_rejected(self, client: AsyncClient) -> None:
        host = await _register(client, "ph3host@procto.dev", "Host")
        student = await _register(client, "ph3student@procto.dev", "Student")
        meeting = await _create_exam(client, host["access_token"])

        ws_student = await _join_exam_via_ws(client, meeting, student)
        await ws_student.send(_envelope("proctor.event", {"signal": "nonsense"}))
        error = await ws_student.receive_type("error")
        assert error["payload"]["code"] == "invalid_signal"
        await ws_student.close()

    async def test_standard_meeting_rejects_signals(self, client: AsyncClient) -> None:
        host = await _register(client, "ph4host@procto.dev", "Host")
        student = await _register(client, "ph4student@procto.dev", "Student")
        meeting_response = await client.post(
            "/api/v1/meetings",
            json={"title": "Regular"},
            headers={"Authorization": f"Bearer {host['access_token']}"},
        )
        meeting = meeting_response.json()

        ws_student = _ws(meeting["code"], student["access_token"])
        await ws_student.connect()
        await ws_student.send(_envelope("sync"))
        await ws_student.receive_type("sync.state")

        await ws_student.send(_envelope("proctor.event", {"signal": "speaking"}))
        error = await ws_student.receive_type("error")
        assert error["payload"]["code"] == "not_proctored"
        await ws_student.close()

    async def test_host_signals_are_ignored(self, client: AsyncClient) -> None:
        host = await _register(client, "ph5host@procto.dev", "Host")
        meeting = await _create_exam(client, host["access_token"])

        ws_host = _ws(meeting["code"], host["access_token"])
        await _connect_ready(ws_host)
        await ws_host.send(_envelope("proctor.event", {"signal": "speaking"}))
        with pytest.raises(TimeoutError):
            await ws_host.receive_type("proctor.flag", timeout=0.4)

        async with SessionLocal() as session:
            count = len((await session.scalars(select(ProctorEvent))).all())
        assert count == 0
        await ws_host.close()


class TestExamReport:
    async def test_report_lists_present_absent_and_scores(self, client: AsyncClient) -> None:
        host = await _register(client, "rhost@procto.dev", "Host")
        student = await _register(client, "rstudent@procto.dev", "Student")
        meeting = await _create_exam(
            client, host["access_token"], invites=["rstudent@procto.dev", "absent@procto.dev"]
        )

        ws_student = await _join_exam_via_ws(client, meeting, student)
        await ws_student.send(
            _envelope("proctor.event", {"signal": "looking_away", "duration_s": 2.5})
        )
        await ws_student.send(_envelope("proctor.event", {"signal": "no_face"}))
        await ws_student.close()

        response = await client.get(
            f"/api/v1/meetings/{meeting['code']}/report",
            headers={"Authorization": f"Bearer {host['access_token']}"},
        )

        assert response.status_code == 200, response.text
        report = response.json()
        assert report["kind"] == "exam"
        by_email = {s["email"]: s for s in report["students"]}
        assert by_email["rstudent@procto.dev"]["status"] == "PRESENT"
        assert by_email["rstudent@procto.dev"]["cheating_score"] == 2 + 3
        assert len(by_email["rstudent@procto.dev"]["events"]) == 2
        assert by_email["absent@procto.dev"]["status"] == "ABSENT"
        assert by_email["absent@procto.dev"]["cheating_score"] == 0

    async def test_report_is_host_only(self, client: AsyncClient) -> None:
        host = await _register(client, "r2host@procto.dev", "Host")
        student = await _register(client, "r2student@procto.dev", "Student")
        meeting = await _create_exam(client, host["access_token"])

        response = await client.get(
            f"/api/v1/meetings/{meeting['code']}/report",
            headers={"Authorization": f"Bearer {student['access_token']}"},
        )
        assert response.status_code == 403

    async def test_csv_download(self, client: AsyncClient) -> None:
        host = await _register(client, "r3host@procto.dev", "Host")
        student = await _register(client, "r3student@procto.dev", "Student")
        meeting = await _create_exam(client, host["access_token"], invites=["ghost@procto.dev"])

        ws_student = await _join_exam_via_ws(client, meeting, student)
        await ws_student.send(_envelope("proctor.event", {"signal": "speaking"}))
        await ws_student.close()

        response = await client.get(
            f"/api/v1/meetings/{meeting['code']}/report.csv",
            headers={"Authorization": f"Bearer {host['access_token']}"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        body = response.text
        assert "r3student@procto.dev" in body
        assert "PRESENT" in body
        assert "speaking" in body
        assert "ghost@procto.dev" in body
        assert "ABSENT" in body


class TestSnapshot:
    async def test_host_snapshot_carries_kind_and_flags(self, client: AsyncClient) -> None:
        host = await _register(client, "shost@procto.dev", "Host")
        student = await _register(client, "sstudent@procto.dev", "Student")
        meeting = await _create_exam(client, host["access_token"])

        ws_student = await _join_exam_via_ws(client, meeting, student)
        await ws_student.send(_envelope("proctor.event", {"signal": "no_face"}))
        await ws_student.close()

        ws_host = _ws(meeting["code"], host["access_token"])
        payload = await _connect_ready(ws_host)

        assert payload["meeting"]["kind"] == "exam"
        assert payload["meeting"]["proctoring_enabled"] is True
        flags = payload.get("proctor_flags", [])
        assert any(f["signal"] == "no_face" for f in flags)
        await ws_host.close()

    async def test_student_snapshot_hides_flags(self, client: AsyncClient) -> None:
        host = await _register(client, "sh2host@procto.dev", "Host")
        student = await _register(client, "sh2student@procto.dev", "Student")
        meeting = await _create_exam(client, host["access_token"])

        async with SessionLocal() as session:
            row = await session.get(Meeting, meeting["id"])
            assert row is not None
            row.waiting_room = False
            await session.commit()
        ws_student = WsTestClient(
            fastapi_app,
            f"/api/v1/ws/meetings/{meeting['code']}",
            query={"token": student["access_token"], "password": EXAM_PASSWORD},
        )
        await ws_student.connect()
        student_payload = await ws_student.receive_type("sync.state")
        assert student_payload["payload"]["meeting"]["kind"] == "exam"
        assert "proctor_flags" not in student_payload["payload"]
        await ws_student.close()
