import json
import logging
import os
import typing as ty
from pathlib import Path, PurePath

from fileformats.application import Json, Pdf
from fileformats.core import extra_implementation
from fileformats.generic import UnicodeFile
from fileformats.medimage.base import MedicalImagingData

from fileformats.vendor.canfield.medimage import (
    DexiDataDir,
    LesionAnalysisDir,
    TomSeedLog,
    TomTrackLog,
    TrackedDir,
    VectraExport,
    WholeBodyCapture,
)
from fileformats.vendor.canfield.medimage.whole_body import Cptr, Sfcm, Tom

logger = logging.getLogger(__name__)


# The containers are copied by `deidentify_nested`, which deidentifies the formats
# nested within them (their validated properties) with their own implementations,
# and then their own files that may contain PHI are deidentified in place in the copy.
# `deidentify` stages the output, so it is only moved into the requested directory
# once it is complete.


@extra_implementation(MedicalImagingData.deidentify)
def vectra_deidentify(
    export_dir: VectraExport,
    out_dir: os.PathLike[str],
    recipe: None = None,
    **kwargs: ty.Any,
) -> VectraExport:
    """
    Deidentifies a Canfield data export directory, deidentifying the whole-body
    captures and lesion analyses within it and redacting its DermX PDF reports.

    Parameters
    ----------
    export_dir: VectraExport
        The directory containing the Canfield data export directory to be deidentified.
    out_dir: PathLike
        The directory where the deidentified files should be written.
    recipe: None
        Canfield exports don't take a deidentification recipe

    Returns
    -------
    VectraExport
        The deidentified VectraExport object.
    """
    deidentified = export_dir.deidentify_nested(out_dir, **kwargs)
    for report in deidentified.dermx_reports:
        pdf_report_deidentify(report)
    return deidentified


@extra_implementation(MedicalImagingData.deidentify)
def vectra_3d_capture_deidentify(
    capture_dir: WholeBodyCapture,
    out_dir: os.PathLike[str],
    recipe: None = None,
    **kwargs: ty.Any,
) -> WholeBodyCapture:

print(">>> vectra_3d_capture_deidentify CALLED")

    deidentified = capture_dir.deidentify_nested(out_dir, **kwargs)
    if deidentified.sglue_log_file:
        sglue_log_deidentify(deidentified.sglue_log_file)
    return deidentified


@extra_implementation(MedicalImagingData.deidentify)
def tracked_dir_deidentify(
    tracked_dir: TrackedDir,
    out_dir: os.PathLike[str],
    recipe: None = None,
    **kwargs: ty.Any,
) -> TrackedDir:
    deidentified = tracked_dir.deidentify_nested(out_dir, **kwargs)
    tracking_log_deidentify(deidentified.tracking_log_file)
    return deidentified


@extra_implementation(MedicalImagingData.deidentify)
def lesion_analysis_deidentify(
    lesion_dir: LesionAnalysisDir,
    out_dir: os.PathLike[str],
    recipe: None = None,
    **kwargs: ty.Any,
) -> LesionAnalysisDir:
    # Registered explicitly (rather than relying on the default for `contains_phi =
    # "nested"`) so callers can look up that it doesn't take a recipe
    return lesion_dir.deidentify_nested(out_dir, **kwargs)


@extra_implementation(MedicalImagingData.deidentify)
def dexi_data_dir_deidentify(
    dexi_data_dir: DexiDataDir,
    out_dir: os.PathLike[str],
    recipe: None = None,
    **kwargs: ty.Any,
) -> DexiDataDir:
    deidentified = dexi_data_dir.deidentify_nested(out_dir, **kwargs)
    result_json_deidentify(deidentified.result_file)
    return deidentified


@extra_implementation(MedicalImagingData.deidentify)
def copy_unchanged_deidentify(
    fileset: Tom | Sfcm | Cptr,
    out_dir: os.PathLike[str],
    recipe: None = None,
    **kwargs: ty.Any,
) -> Tom | Sfcm | Cptr:
    """The 3D mesh, calibration and capture-settings files have no known identifying
    metadata to strip, so are copied unchanged (as they were before nested
    deidentification required an implementation for every nested format that may
    contain PHI)"""
    return fileset.copy(Path(out_dir), make_dirs=True)


def pdf_report_deidentify(pdf_report: Pdf) -> Pdf:
    """
    De-identifies the DermX PDF reports by replacing the contents with "Report redacted"
    Parameters:
    - pdf_report: Path to the PDF report file
    Returns:
    - PDF file contents for writing the de-identified PDF
    """
    if not pdf_report.name.startswith("DermX Report"):
        raise ValueError(f"Expected a DermX Report PDF, but got '{pdf_report.name}'")

    content = "BT /F1 24 Tf 72 700 Td (Report redacted) Tj ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] ",
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = "%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(pdf.encode("latin-1")))
        pdf += f"{i} 0 obj\n{obj}\nendobj\n"

    xref_start = len(pdf.encode("latin-1"))
    pdf += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n"
    pdf += "".join(f"{off:010d} 00000 n \n" for off in offsets)
    pdf += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF"
    pdf_report.fspath.write_bytes(pdf.encode("latin-1"))

    return pdf_report


def result_json_deidentify(result_json: Json) -> Json:
    """
    De-identify the `result.json` file generated by DEXI version 1, in place
    Replaces the `ImageLocation` field in each `OutputImages` entry with just the filename, removing any directory paths.
    Parameters:
    - result_json: Path to the `result.json` file
    Returns:
    - The de-identified `result.json` file
    """
    if result_json.name != "result.json":
        raise ValueError(f"Expected 'result.json', but got '{result_json.name}'")

    if result_json.fspath.parent.name != "DexiData":
        return result_json

    with open(result_json) as resultjson_contents:
        json_data = json.load(resultjson_contents)

    algorithms = json_data.get("Algorithms", [])
    if not isinstance(algorithms, list):
        logger.warning("Algorithms is not a list.")
        return result_json

    for algorithm in algorithms:
        if not isinstance(algorithm, dict):
            continue

        output_images = algorithm.get("OutputImages", [])

        if not isinstance(output_images, list):
            logger.warning("OutputImages is not a list.")
            continue

        for image in output_images:
            if not isinstance(image, dict):
                continue

            location = image.get("ImageLocation")
            if location and isinstance(location, str):
                image["ImageLocation"] = PurePath(location).name

    result_json.fspath.write_text(json.dumps(json_data, indent=4))
    return result_json


def log_file_deidentify(
    log_file: UnicodeFile, sensitive_line_prefixes: str | tuple[str, ...]
) -> UnicodeFile:
    """
    De-identify a log file by removing lines that start with specified sensitive prefixes.
    Parameters:
    - log_file: Path to the log file
    - sensitive_line_prefixes: A string or tuple of strings representing the prefixes of lines to remove
    Returns:
    - A string containing the de-identified log contents
    """
    log_file.fspath.write_text(_filter_log_lines(log_file, sensitive_line_prefixes))
    return log_file


def sglue_log_deidentify(log_file: UnicodeFile) -> UnicodeFile:
    """
    De-identify the `sglue-log.txt` file by removing lines that start with "cmd line as invoked".
    Parameters:
    - log_file: Path to the `sglue-log.txt` file
    Returns:
    - A string containing the de-identified log contents
    """
    if log_file.name != "sglue-log.txt":
        raise ValueError(f"Expected 'sglue-log.txt', but got '{log_file.name}'")
    file_specific_prefixes = "cmd line as invoked"
    return log_file_deidentify(log_file, file_specific_prefixes)


@extra_implementation(MedicalImagingData.deidentify)
def tom_seed_log_deidentify(
    tom_seed_log: TomSeedLog,
    out_dir: os.PathLike[str],
    recipe: None = None,
    **kwargs: ty.Any,
) -> TomSeedLog:
    """
    De-identify the `tom-seed.log` file by removing lines that start with "loading"
    or "loaded".
    Parameters:
    - tom_seed_log: Path to the `tom-seed.log` file
    - out_dir: The directory to write the de-identified copy of the log to
    Returns:
    - The de-identified log file
    """
    if not tom_seed_log.name.endswith("tom-seed.log"):
        raise ValueError(f"Expected 'tom-seed.log', but got '{tom_seed_log.name}'")
    deidentified = tom_seed_log.copy(Path(out_dir), make_dirs=True)
    log_file_deidentify(deidentified, ("loading", "loaded"))
    return deidentified


@extra_implementation(MedicalImagingData.deidentify)
def tom_track_log_deidentify(
    tom_track_log: TomTrackLog,
    out_dir: os.PathLike[str],
    recipe: None = None,
    **kwargs: ty.Any,
) -> TomTrackLog:
    """
    De-identify the `tom-track.log` file by removing lines that start with
    "no images" or "mesh vertex".
    Parameters:
    - tom_track_log: Path to the `tom-track.log` file
    - out_dir: The directory to write the de-identified copy of the log to
    Returns:
    - The de-identified log file
    """
    if not tom_track_log.name.endswith("tom-track.log"):
        raise ValueError(f"Expected 'tom-track.log', but got '{tom_track_log.name}'")
    deidentified = tom_track_log.copy(Path(out_dir), make_dirs=True)
    log_file_deidentify(deidentified, ("no images", "mesh vertex"))
    return deidentified


def _filter_log_lines(
    log_file: UnicodeFile, sensitive_line_prefixes: str | tuple[str, ...]
) -> str:
    """The contents of the log file without the lines that start with the prefixes"""
    with open(log_file) as log_contents:
        return "".join(
            line
            for line in log_contents
            if not line.startswith(sensitive_line_prefixes)
        )


def tracking_log_deidentify(log_file: UnicodeFile) -> UnicodeFile:
    """
    De-identify the `tracking-log.txt` file by removing all contents.
    Parameters:
    - log_file: Path to the `tracking-log.txt` file
    Returns:
    - An empty string, effectively removing all contents of the log
    """
    if log_file.name != "tracking-log.txt":
        raise ValueError(f"Expected 'tracking-log.txt', but got '{log_file.name}'")
    return log_file_deidentify(log_file, "")
