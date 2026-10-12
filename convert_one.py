import argparse
from pathlib import Path
from markitdown import MarkItDown

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source = Path(args.input).resolve()
    output = Path(args.output).resolve()

    # Không bật plugin mở rộng khi xử lý tài liệu không tin cậy.
    result = MarkItDown(enable_plugins=False).convert_local(str(source))

    # text_content là nội dung Markdown trong API phổ biến của MarkItDown.
    content = getattr(result, "text_content", None)
    if content is None:
        content = getattr(result, "markdown", None)
    if content is None:
        raise RuntimeError("Không tìm thấy nội dung Markdown trong kết quả")

    output.write_text(content, encoding="utf-8")

if __name__ == "__main__":
    main()