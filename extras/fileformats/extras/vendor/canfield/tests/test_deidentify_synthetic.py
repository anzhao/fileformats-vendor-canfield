"""Deidentification of a synthetic export with the layout of a real one, so it can be
tested without the export test data"""

import json
import typing as ty
from collections import Counter
from pathlib import Path

import pytest

from fileformats.medimage import MedicalImagingData
from fileformats.vendor.canfield.medimage import (
    DexiDataDir,
    LesionAnalysisDir,
    TomSeedLog,
    TomTrackLog,
    TrackedDir,
    VectraExport,
    WholeBodyCapture,
)
from fileformats.vendor.canfield.medimage.lesion import DanaosDir, T2k
from fileformats.vendor.canfield.medimage.whole_body import (
    CalibDir,
    Cptr,
    Sfcm,
    Tom,
    WholeBodyAnalysisDir,
)

CANFIELD_TYPES = (
    VectraExport,
    WholeBodyCapture,
    CalibDir,
    WholeBodyAnalysisDir,
    TrackedDir,
    LesionAnalysisDir,
    DexiDataDir,
    DanaosDir,
    T2k,
    Tom,
    Sfcm,
    Cptr,
    TomSeedLog,
    TomTrackLog,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


def _write(path: Path, contents: str | bytes = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(contents, bytes):
        path.write_bytes(contents)
    else:
        path.write_text(contents)


def _make_export(root: Path) -> VectraExport:
    export = root / "export"
    _write(export / "20240730103101.t2k", b"encrypted")
    _write(export / "DermX Report 1.pdf", "%PDF-1.4\nJane Doe\n%%EOF")

    capture = export / "20240730103101"
    _write(capture / "20240730103101.tom", b"mesh")
    _write(capture / "capture.cptr", b"capture")
    for name in ("a3d-config.ini", "context", "Dcontext", "camerainfo", "flashstatus"):
        _write(capture / name, "settings")
    _write(capture / "1C.png", PNG)
    _write(capture / "sglue-log.txt", "cmd line as invoked: Jane Doe\nok\n")
    _write(capture / "calib" / "a10A.sfcm", b"map")
    for name in ("adjustframe.euc", "info", "tag"):
        _write(capture / "calib" / name, b"calib")
    _write(capture / "analysis" / "lesion_data_1.json", "{}")
    _write(capture / "analysis" / "exitstatus_1.txt", "0")
    _write(capture / "analysis" / "LESION_ANALYSIS_1", b"analysis")
    tracked = capture / "Tracked_guid"
    _write(tracked / "track_template_1.tom", b"template")
    _write(tracked / "1.tom-seed.log", "loading Jane Doe\nseeded\n")
    _write(tracked / "1.tom-track.log", "mesh vertex Jane Doe\ntracked\n")
    _write(tracked / "tracking-log.txt", "Jane Doe\n")
    _write(tracked / "lms" / "procstatus", "done")

    lesion = export / "20240730104500"
    _write(lesion / "captureinfo_scope", "scope")
    _write(lesion / "DexiData" / "lesion.png", PNG)
    _write(
        lesion / "DexiData" / "result.json",
        json.dumps(
            {
                "Algorithms": [
                    {
                        "AlgorithmName": "alg",
                        "OutputImages": [
                            {
                                "Name": "lesion",
                                "ContentType": "png",
                                "ImageLocation": "lesion.png",
                            }
                        ],
                    }
                ]
            }
        ),
    )
    return VectraExport(export)


def test_deidentify_synthetic_export(tmp_path: Path) -> None:
    export = _make_export(tmp_path / "in")
    out_dir = tmp_path / "out"
    deidentified = export.deidentify(out_dir)

    assert isinstance(deidentified, VectraExport)
    assert deidentified.fspath == out_dir / "export"
    # The same files are written in the same layout, and nothing else
    assert sorted(
        p.relative_to(deidentified.fspath) for p in deidentified.all_file_paths()
    ) == sorted(p.relative_to(export.fspath) for p in export.all_file_paths())
    assert sorted(p.name for p in out_dir.iterdir()) == ["export"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["in", "out"]

    out = deidentified.fspath
    for path in out.rglob("*"):
        if path.is_file() and path.suffix in (".txt", ".log", ".pdf"):
            assert "Jane Doe" not in path.read_text(errors="ignore"), path
    capture = out / "20240730103101"
    assert (capture / "sglue-log.txt").read_text() == "ok\n"
    assert (capture / "Tracked_guid" / "1.tom-seed.log").read_text() == "seeded\n"
    assert (capture / "Tracked_guid" / "1.tom-track.log").read_text() == "tracked\n"
    assert (capture / "Tracked_guid" / "tracking-log.txt").read_text() == ""
    assert (capture / "20240730103101.tom").read_bytes() == b"mesh"
    assert "Report redacted" in (out / "DermX Report 1.pdf").read_text()

    # The source is left untouched
    assert (
        "Jane Doe" in (export.fspath / "20240730103101" / "sglue-log.txt").read_text()
    )


def test_deidentify_synthetic_export_failure_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fileformats.extras.vendor.canfield import medimage as extras

    def fail(_: object) -> None:
        raise RuntimeError("redaction failed")

    monkeypatch.setattr(extras, "pdf_report_deidentify", fail)
    out_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="redaction failed"):
        _make_export(tmp_path / "in").deidentify(out_dir)
    assert not out_dir.exists()
    # the staging directories are cleaned up
    assert sorted(p.name for p in tmp_path.iterdir()) == ["in"]


@pytest.fixture
def deidentify_calls() -> ty.Iterator[Counter[str]]:
    """Counts the calls to the deidentify implementation of each Canfield type, by
    wrapping the implementations registered for them (or the default for those without
    one) with a recorder"""
    dispatch = MedicalImagingData.deidentify._dispatch  # type: ignore[attr-defined]
    calls: Counter[str] = Counter()
    originals = {tp: dispatch.dispatch(tp) for tp in CANFIELD_TYPES}

    def recorder(tp: type, implementation: ty.Any) -> ty.Any:
        def record(fileset: ty.Any, *args: ty.Any, **kwargs: ty.Any) -> ty.Any:
            calls[tp.__name__] += 1
            return implementation(fileset, *args, **kwargs)

        return record

    for tp, implementation in originals.items():
        dispatch.register(tp, recorder(tp, implementation))
    try:
        yield calls
    finally:
        for tp, implementation in originals.items():
            dispatch.register(tp, implementation)


def test_deidentify_synthetic_export_calls_all_nested(
    tmp_path: Path, deidentify_calls: Counter[str]
) -> None:
    _make_export(tmp_path / "in").deidentify(tmp_path / "out")

    assert deidentify_calls == {
        "VectraExport": 1,
        "WholeBodyCapture": 1,
        # the capture's mesh and the tracking template
        "Tom": 2,
        "Cptr": 1,
        "CalibDir": 1,
        "Sfcm": 1,
        "WholeBodyAnalysisDir": 1,
        "TrackedDir": 1,
        "TomSeedLog": 1,
        "TomTrackLog": 1,
        "LesionAnalysisDir": 1,
        "DexiDataDir": 1,
    }
