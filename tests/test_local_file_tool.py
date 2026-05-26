import tempfile
from pathlib import Path
from tools.local_file_tool import ReadLocalLectureFilesTool


class TestReadLocalLectureFilesTool:
    """Test the PDF/PPTX file reading tool."""

    def test_empty_folder(self):
        tool = ReadLocalLectureFilesTool()
        with tempfile.TemporaryDirectory() as tmp:
            result = tool._run(folder_path=tmp)
            assert "No PDF or PPT files found" in result

    def test_nonexistent_folder(self):
        tool = ReadLocalLectureFilesTool()
        result = tool._run(folder_path="/nonexistent/path/xyz")
        assert "does not exist" in result

    def test_skips_non_lecture_files(self):
        tool = ReadLocalLectureFilesTool()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "notes.txt").write_text("hello")
            (Path(tmp) / "image.png").write_text("fake")
            result = tool._run(folder_path=tmp)
            assert "No PDF or PPT files found" in result
