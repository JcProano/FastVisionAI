"""Run Guided Face Capture with safe aggregate profile diagnostics enabled."""

from src.validation.guided_face_capture import main as guided_main


def main() -> int:
    return guided_main(diagnostics_enabled=True)


if __name__ == "__main__":
    raise SystemExit(main())
