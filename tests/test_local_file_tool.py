import tempfile
from pathlib import Path
from tools.local_file_tool import ReadLocalLectureFilesTool


class TestReadLocalLectureFilesTool:
    """Test the PDF/PPTX file reading tool."""

    def test_empty_folder(self):
        tool = ReadLocalLectureFilesTool()
        with tempfile.TemporaryDirectory() as tmp:
            result = tool._run(folder_path=tmp)
            assert "未找到 PDF 或 PPT 文件" in result

    def test_nonexistent_folder(self):
        tool = ReadLocalLectureFilesTool()
        result = tool._run(folder_path="/nonexistent/path/xyz")
        assert "不存在" in result

    def test_skips_non_lecture_files(self):
        tool = ReadLocalLectureFilesTool()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "notes.txt").write_text("hello")
            (Path(tmp) / "image.png").write_text("fake")
            result = tool._run(folder_path=tmp)
            assert "未找到 PDF 或 PPT 文件" in result
