import io
import unittest

from fastapi import UploadFile

from app.services.file_parser import extract_text_from_upload


class FileParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_text_from_txt_file(self) -> None:
        upload = UploadFile(filename="memo.txt", file=io.BytesIO(b"Hello parser"))
        text = await extract_text_from_upload(
            file=upload,
            max_file_bytes=1024 * 1024,
            allowed_extensions={".txt", ".pdf", ".md", ".csv"},
            debug_logging=False,
        )
        self.assertEqual(text, "Hello parser")

    async def test_rejects_unsupported_extension(self) -> None:
        upload = UploadFile(filename="binary.exe", file=io.BytesIO(b"abc"))
        with self.assertRaises(ValueError) as ctx:
            await extract_text_from_upload(
                file=upload,
                max_file_bytes=1024 * 1024,
                allowed_extensions={".txt", ".pdf", ".md", ".csv"},
                debug_logging=False,
            )
        self.assertIn("Unsupported file type", str(ctx.exception))

    async def test_rejects_oversize_file(self) -> None:
        upload = UploadFile(filename="memo.txt", file=io.BytesIO(b"a" * 11))
        with self.assertRaises(ValueError) as ctx:
            await extract_text_from_upload(
                file=upload,
                max_file_bytes=10,
                allowed_extensions={".txt", ".pdf", ".md", ".csv"},
                debug_logging=False,
            )
        self.assertIn("File is too large", str(ctx.exception))
