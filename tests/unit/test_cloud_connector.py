"""Cloud-connector parity fixtures 1 (create-payload) and 2 (read hydration).

The JSON shapes and assertions mirror the canonical fixtures shared across every
SDK (``api2convert-cloud-connector-parity-fixtures.md``), plus unit coverage of
the new cloud value types. Mirrors the PHP ``CloudConnectorTest``.
"""

from __future__ import annotations

from collections.abc import Callable

from api2convert import Api2Convert, CloudInput, CloudProvider, Job, OutputTarget

from ..conftest import MockAPI

# The exact input descriptor fixture 1 expects the SDK to serialize.
EXPECTED_INPUT = {
    "type": "cloud",
    "source": "amazons3",
    "parameters": {"bucket": "my-bucket", "file": "in/photo.png"},
    "credentials": {"accesskeyid": "AKIA_TEST", "secretaccesskey": "SECRET_TEST"},
}

# The exact output_target descriptor fixture 1 expects — note: no `status` key.
EXPECTED_OUTPUT_TARGET = {
    "type": "ftp",
    "parameters": {"host": "ftp.example.com", "file": "/out/photo.jpg"},
    "credentials": {"username": "u", "password": "p"},
}


# ---- Fixture 1: create-payload (what convert() serializes) ------------------------------


def test_fixture1_convert_serializes_cloud_input_and_output_target(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    # create -> started job; wait() polls once to a completed job with no local output.
    api.add_json(201, {"id": "job-1", "status": {"code": "incomplete"}})
    api.add_json(200, {"id": "job-1", "status": {"code": "completed"}})

    cloud_input = CloudInput.amazon_s3(
        bucket="my-bucket",
        file="in/photo.png",
        accesskeyid="AKIA_TEST",
        secretaccesskey="SECRET_TEST",
    )
    target = OutputTarget(
        "ftp",
        {"host": "ftp.example.com", "file": "/out/photo.jpg"},
        {"username": "u", "password": "p"},
    )

    make_client().convert(cloud_input, "jpg", output_targets=[target])

    body = api.json_at(0)

    # 1) a cloud input is a started job (like a remote URL), not staged/uploaded.
    assert body["process"] is True

    # 2) input[0] carries the flat/lowercase keys exactly as the factory emits them.
    assert body["input"] == [EXPECTED_INPUT]

    # 3) conversion[0].output_target[0] serializes {type,parameters,credentials} and NO status.
    assert body["conversion"][0]["output_target"] == [EXPECTED_OUTPUT_TARGET]
    assert "status" not in body["conversion"][0]["output_target"][0]

    # output targets never leak into the conversion options map.
    assert "options" not in body["conversion"][0]


def test_fixture1_raw_create_path_produces_byte_identical_output_target(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(201, {"id": "job-1", "status": {"code": "completed"}})

    make_client().jobs.create(
        {
            "process": True,
            "input": [
                CloudInput.amazon_s3(
                    "my-bucket", "in/photo.png", "AKIA_TEST", "SECRET_TEST"
                ).to_dict()
            ],
            "conversion": [
                {
                    "target": "jpg",
                    "output_target": [
                        OutputTarget.of(
                            CloudProvider.FTP,
                            {"host": "ftp.example.com", "file": "/out/photo.jpg"},
                            {"username": "u", "password": "p"},
                        ).to_dict()
                    ],
                }
            ],
        }
    )

    body = api.json_at(0)

    # Both the convert() output_targets control and the raw create map yield the same bytes.
    assert body["input"] == [EXPECTED_INPUT]
    assert body["conversion"][0]["output_target"] == [EXPECTED_OUTPUT_TARGET]


def test_add_input_accepts_cloud_input_builder(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(200, {"id": "in-1", "type": "cloud", "source": "ftp"})

    make_client().jobs.add_input("job-1", CloudInput.ftp("ftp.example.com", "in/a.png", "u", "p"))

    body = api.json_at(0)
    assert body["type"] == "cloud"
    assert body["source"] == "ftp"
    assert body["parameters"] == {"host": "ftp.example.com", "file": "in/a.png"}
    assert body["credentials"] == {"username": "u", "password": "p"}


# ---- Fixture 2: read hydration (a GET /jobs/{id} response) ------------------------------


def test_fixture2_hydrates_cloud_input_and_output_target() -> None:
    job = Job.from_dict(
        {
            "id": "job-1",
            "status": {"code": "completed"},
            "input": [
                {
                    "id": "in-1",
                    "type": "cloud",
                    "source": "amazons3",
                    "status": "ready",
                    "parameters": {"bucket": "my-bucket", "file": "in/photo.png"},
                    "credentials": {},
                }
            ],
            "conversion": [
                {
                    "id": "c-1",
                    "target": "jpg",
                    "output_target": [
                        {
                            "type": "ftp",
                            "parameters": {"host": "ftp.example.com", "file": "/out/photo.jpg"},
                            "credentials": {},
                            "status": "uploading",
                        }
                    ],
                }
            ],
        }
    )

    # 1) input source is a RAW string; parameters surface.
    input_file = job.input[0]
    assert input_file.source == "amazons3"
    assert input_file.status == "ready"
    assert input_file.parameters == {"bucket": "my-bucket", "file": "in/photo.png"}

    # 2) output target status/parameters/type surface.
    target = job.conversion[0].output_targets[0]
    assert target.type == "ftp"
    assert target.status == "uploading"
    assert target.parameters == {"host": "ftp.example.com", "file": "/out/photo.jpg"}

    # 3) credentials are never surfaced (the API returns them empty; the SDK does not hydrate).
    assert target.credentials == {}


def test_fixture2_unknown_provider_round_trips_untyped() -> None:
    job = Job.from_dict(
        {
            "id": "job-1",
            "status": {"code": "completed"},
            "input": [{"id": "in-1", "type": "cloud", "source": "r2", "status": "ready"}],
            "conversion": [
                {"target": "jpg", "output_target": [{"type": "r2", "status": "waiting"}]}
            ],
        }
    )

    # An unknown provider string hydrates without any enum parse throwing.
    assert job.input[0].source == "r2"
    assert job.conversion[0].output_targets[0].type == "r2"
    assert job.conversion[0].output_targets[0].status == "waiting"


# ---- Unit: the new value types ---------------------------------------------------------


def test_cloud_provider_vocabulary() -> None:
    assert [provider.value for provider in CloudProvider] == [
        "amazons3",
        "azure",
        "ftp",
        "gdrive",
        "googlecloud",
        "youtube",
    ]


def test_per_provider_constructors_carry_required_keys_verbatim() -> None:
    assert CloudInput.azure("c", "f", "n", "k").to_dict() == {
        "type": "cloud",
        "source": "azure",
        "parameters": {"container": "c", "file": "f"},
        "credentials": {"accountname": "n", "accountkey": "k"},
    }
    assert CloudInput.google_cloud("p", "b", "f", "kf").to_dict() == {
        "type": "cloud",
        "source": "googlecloud",
        "parameters": {"projectid": "p", "bucket": "b", "file": "f"},
        "credentials": {"keyfile": "kf"},
    }


def test_generic_escape_hatch_carries_forward_compat_keys() -> None:
    cloud_input = CloudInput.amazon_s3(
        "b", "f", "id", "sec", parameters={"region": "eu"}, credentials={"sessiontoken": "t"}
    )

    assert cloud_input.parameters == {"bucket": "b", "file": "f", "region": "eu"}
    assert cloud_input.credentials == {
        "accesskeyid": "id",
        "secretaccesskey": "sec",
        "sessiontoken": "t",
    }


def test_output_target_omits_status_on_serialize_but_hydrates_it_on_read() -> None:
    created = OutputTarget("ftp", {"host": "h"}, {"username": "u"}, status="completed")
    assert "status" not in created.to_dict()

    read = OutputTarget.from_dict(
        {"type": "ftp", "parameters": {"host": "h"}, "status": "completed"}
    )
    assert read.status == "completed"
    assert read.credentials == {}
