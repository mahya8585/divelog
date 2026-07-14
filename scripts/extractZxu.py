"""Move Z-X files from scripts/folders into scripts/result."""

from pathlib import Path
import shutil


SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_DIR = SCRIPT_DIR / "folders"
DESTINATION_DIR = SCRIPT_DIR / "result"


def move_zxu_files(source_dir: Path = SOURCE_DIR, destination_dir: Path = DESTINATION_DIR) -> int:
	"""Move all .zxu files below source_dir and return the number moved."""
	if not source_dir.is_dir():
		raise FileNotFoundError(f"Source directory does not exist: {source_dir}")

	destination_dir.mkdir(parents=True, exist_ok=True)
	moved_count = 0

	for source_path in source_dir.rglob("*"):
		if not source_path.is_file() or source_path.suffix.lower() != ".zxu":
			continue

		destination_path = destination_dir / source_path.name
		if destination_path.exists():
			raise FileExistsError(f"Destination file already exists: {destination_path}")

		shutil.move(str(source_path), str(destination_path))
		print(f"Moved: {source_path} -> {destination_path}")
		moved_count += 1

	return moved_count


if __name__ == "__main__":
	count = move_zxu_files()
	print(f"Moved {count} .zxu file(s).")
