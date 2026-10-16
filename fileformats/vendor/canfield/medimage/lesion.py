import typing as ty

from fileformats.application import Json, Xml
from fileformats.core import from_mime, mtime_cached_property, validated_property
from fileformats.core.exceptions import FormatMismatchError
from fileformats.generic import BinaryFile, Directory, FileSet, UnicodeFile
from fileformats.image import Png
from fileformats.medimage import MedicalImagingData


class T2k(BinaryFile, MedicalImagingData):
    """Canfield Vectra image data

    Canfield encrypted proprietary image file format, presumably generated
    by the hand-held Vectra H1 camera. The file contains a set of images and metadata
    for a single capture, including the original images, the processed images,
    and the results of lesion analysis. The file is encrypted and can only be read
    by Canfield's proprietary software. The file is typically named with a
    timestamp and a .t2k extension, e.g. '20240730103101.t2k'.
    """

    ext = ".t2k"


class DexiDataDir(Directory, MedicalImagingData):
    """Canfield Dexi image data directory"""

    @mtime_cached_property
    def result_dict(self) -> dict[ty.Any, ty.Any]:
        """The results file in the directory."""
        return self.result_file.load()  # type: ignore[no-any-return]

    @validated_property  # validated_property is checked at initialization time, so if this file is missing the format will not match
    def result_file(self) -> Json:
        """The results file in the directory."""
        return Json(self.fspath / "result.json")

    @validated_property
    def output_images(self) -> dict[str, dict[str, FileSet]]:
        output_images: dict[str, dict[str, FileSet]] = {}
        for alg in self.result_dict["Algorithms"]:
            alg_out = output_images[alg["AlgorithmName"]] = {}
            for img in alg["OutputImages"]:
                mime_type = img["ContentType"]
                if mime_type == "jpg":
                    mime_type = "image/jpeg"
                elif mime_type in ["svg", "image/svg"]:
                    mime_type = "image/svg+xml"
                elif "/" not in mime_type:
                    mime_type = f"image/{mime_type}"
                datatype: type[FileSet] = from_mime(mime_type)  # type: ignore[assignment]
                alg_out[img["Name"]] = datatype(self.fspath / img["ImageLocation"])
        if not output_images:
            raise FormatMismatchError(
                f"No output images found in analysis dir results.json:\n{self.result_dict}"
            )
        return output_images


class DanaosDir(Directory, MedicalImagingData):
    """Canfield Danaos image data directory"""

    @validated_property
    def data_file(self) -> Xml:
        """The data file in the directory."""
        return Xml(self.fspath / "Data.xml")

    @property
    def asymmetry_files(self) -> list[Png]:
        """The asymmetry files in the directory."""
        return [Png(self.fspath / f) for f in self.fspath.glob("Asy*.png")]

    @property
    def colour_files(self) -> list[Png]:
        """The colour files in the directory."""
        return [Png(self.fspath / f) for f in self.fspath.glob("Col*.png")]

    @property
    def contour_file(self) -> Png:
        """The contour file in the directory."""
        return Png(self.fspath / "Cont.png")

    @property
    def hair_file(self) -> Png:
        """The hair file in the directory."""
        return Png(self.fspath / "Hair.png")


class LesionAnalysisDir(Directory, MedicalImagingData):
    """Canfield Vectra lesion capture and analysis"""

    contains_phi = "nested"

    @validated_property
    def captureinfo_file(self) -> UnicodeFile:
        """The capture info file in the directory."""
        return UnicodeFile(self.fspath / "captureinfo_scope")

    @validated_property
    def dexi_dirs(self) -> dict[str, DexiDataDir]:
        """Dictionary of dexi directories sorted by their version."""
        dct = {
            (p.name.partition("_")[2] or "1.0"): DexiDataDir(p)
            for p in self.fspath.glob("DexiData*")
            if p.is_dir()
        }
        if not dct:
            raise FormatMismatchError(
                f"Did not find any DexiData sub-directories within the Vectra directory path {self.fspath}"
            )
        return dct

    @property
    def danaos_dir(self) -> DanaosDir | None:
        """The danaos directory in the directory."""
        path = self.fspath / "DANAOS"
        return DanaosDir(path) if path.exists() else None
