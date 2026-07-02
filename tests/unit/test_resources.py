"""Per-resource HTTP contract: verb, path, query/body shape, model hydration."""

from __future__ import annotations

from collections.abc import Callable

import api2convert
from api2convert import (
    Api2Convert,
    InputFile,
    Job,
    OutputFile,
    Preset,
    WebhookVerifier,
)
from api2convert.resources import (
    ContractsResource,
    ConversionsResource,
    JobsResource,
    PresetsResource,
    StatsResource,
)

from ..conftest import MockAPI


def test_jobs_list_sends_page_and_status(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(
        200,
        [{"id": "a", "status": {"code": "completed"}}, {"id": "b", "status": {"code": "failed"}}],
    )
    jobs = make_client().jobs.list(status="completed", page=2)

    assert [j.id for j in jobs] == ["a", "b"]
    url = str(api.request_at(0).url)
    assert api.request_at(0).method == "GET"
    assert "page=2" in url
    assert "status=completed" in url


def test_jobs_update_patches(make_client: Callable[..., Api2Convert], api: MockAPI) -> None:
    api.add_json(200, {"id": "j", "status": {"code": "processing"}})
    job = make_client().jobs.update("j", {"process": True})

    assert isinstance(job, Job)
    assert api.request_at(0).method == "PATCH"
    assert str(api.request_at(0).url).endswith("/jobs/j")
    assert api.json_at(0) == {"process": True}


def test_jobs_cancel_deletes(make_client: Callable[..., Api2Convert], api: MockAPI) -> None:
    api.add_text(200, "")
    assert make_client().jobs.cancel("j") is None
    assert api.request_at(0).method == "DELETE"
    assert str(api.request_at(0).url).endswith("/jobs/j")


def test_jobs_add_input(make_client: Callable[..., Api2Convert], api: MockAPI) -> None:
    api.add_json(200, {"id": "in-1", "type": "remote", "source": "https://x"})
    descriptor = {"type": "remote", "source": "https://x"}
    result = make_client().jobs.add_input("j", descriptor)

    assert isinstance(result, InputFile)
    assert result.type == "remote"
    assert api.request_at(0).method == "POST"
    assert str(api.request_at(0).url).endswith("/jobs/j/input")
    assert api.json_at(0) == descriptor


def test_jobs_outputs(make_client: Callable[..., Api2Convert], api: MockAPI) -> None:
    api.add_json(200, [{"id": "o", "uri": "https://dl/x", "size": 10}])
    outputs = make_client().jobs.outputs("j")

    assert [type(o) for o in outputs] == [OutputFile]
    assert outputs[0].size == 10
    assert api.request_at(0).method == "GET"
    assert str(api.request_at(0).url).endswith("/jobs/j/output")


def test_conversions_list_filters(make_client: Callable[..., Api2Convert], api: MockAPI) -> None:
    api.add_json(200, [{"target": "png", "category": "image", "options": {}}])
    rows = make_client().conversions.list(category="image", target="png")

    assert rows[0]["target"] == "png"
    url = str(api.request_at(0).url)
    assert "category=image" in url
    assert "target=png" in url


def test_presets_crud(make_client: Callable[..., Api2Convert], api: MockAPI) -> None:
    api.add_json(200, [{"id": "p", "name": "web", "target": "jpg"}])
    api.add_json(200, {"id": "p", "name": "web", "target": "jpg"})
    api.add_json(200, {"id": "p", "name": "web"})
    api.add_json(200, {"id": "p", "name": "web2"})
    api.add_text(200, "")
    client = make_client()

    listed = client.presets.list(target="jpg")
    assert [type(p) for p in listed] == [Preset]
    list_url = str(api.request_at(0).url)
    assert "target=jpg" in list_url
    assert "page=" not in list_url  # presets list has no page param

    created = client.presets.create({"name": "web", "target": "jpg"})
    assert isinstance(created, Preset)
    assert api.request_at(1).method == "POST"
    assert str(api.request_at(1).url).endswith("/presets")

    got = client.presets.get("p")
    assert got.id == "p"
    assert str(api.request_at(2).url).endswith("/presets/p")

    updated = client.presets.update("p", {"name": "web2"})
    assert updated.name == "web2"
    assert api.request_at(3).method == "PATCH"

    assert client.presets.delete("p") is None
    assert api.request_at(4).method == "DELETE"
    assert str(api.request_at(4).url).endswith("/presets/p")


def test_stats_endpoints(make_client: Callable[..., Api2Convert], api: MockAPI) -> None:
    api.add_json(200, {"conversions": 5})
    api.add_json(200, {"conversions": 50})
    api.add_json(200, {"conversions": 500})
    client = make_client()

    assert client.stats.day("2026-07-01") == {"conversions": 5}
    assert str(api.request_at(0).url).endswith("/stats/day/2026-07-01/all")

    client.stats.month("2026-07", filter="my-key")
    assert str(api.request_at(1).url).endswith("/stats/month/2026-07/my-key")

    client.stats.year("2026")
    assert str(api.request_at(2).url).endswith("/stats/year/2026/all")


def test_contracts_get(make_client: Callable[..., Api2Convert], api: MockAPI) -> None:
    api.add_json(200, {"contracts": []})
    assert make_client().contracts.get() == {"contracts": []}
    assert str(api.request_at(0).url).endswith("/contracts")


def test_resource_accessors_and_webhooks(make_client: Callable[..., Api2Convert]) -> None:
    with make_client() as client:
        assert isinstance(client.jobs, JobsResource)
        assert isinstance(client.conversions, ConversionsResource)
        assert isinstance(client.presets, PresetsResource)
        assert isinstance(client.stats, StatsResource)
        assert isinstance(client.contracts, ContractsResource)
        assert isinstance(client.jobs, JobsResource)  # cached, same each access
        assert client.jobs is client.jobs

    assert isinstance(Api2Convert.webhooks(), WebhookVerifier)
    assert isinstance(api2convert.webhooks(), WebhookVerifier)
